import os
import sys
import re
import json
import sox
import shutil
from datetime import datetime
import requests
import firebase_admin

from firebase_admin import credentials, storage
from pydub import AudioSegment
from pedalboard import Pedalboard, Reverb, Delay, Chorus, Gain
from pedalboard.io import AudioFile
import numpy as np

from main import voice_change, find_full_path

def initialize_firebase():
    """Firebase Storage 초기화"""
    if not firebase_admin._apps:
        cred = credentials.Certificate('/content/credentials.release.json')
        firebase_admin.initialize_app(cred, {
            'storageBucket': 'homebrew-prod.appspot.com'
        })
    return storage.bucket()

def apply_reverb(input_path, output_path):
    """TAL-Reverb-4 설정을 최대한 유사하게 구현한 리버브 적용"""
    print(f"[REVERB] Applying TAL-style reverb to {input_path}")
    
    try:
        # 오디오 파일 로드
        with AudioFile(input_path) as f:
            audio = f.read(f.frames)
            samplerate = f.samplerate
            
            # 모노를 스테레오로 변환
            if len(audio.shape) == 1:
                audio = np.stack([audio, audio])
            elif len(audio.shape) == 2 and audio.shape[0] == 1:
                audio = np.stack([audio[0], audio[0]])
            elif len(audio.shape) == 2 and audio.shape[1] == 1:
                audio = np.stack([audio.T[0], audio.T[0]])

            print("Audio shape:", audio.shape)

        # TAL-Reverb-4 설정을 매칭한 이펙트 체인
        board = Pedalboard([
            # Pre-delay (TAL의 delay: 0.1000 s)
            Delay(
                delay_seconds=0.1,
                feedback=0.0,  # 피드백 없음
                mix=1.0       # 100% delay signal
            ),
            
            # Main reverb (TAL의 주요 파라미터 매칭)
            Reverb(
                room_size=0.55,     # size=55.0
                damping=0.2,        # damp=20.0
                wet_level=0.35,     # wet=35.0
                dry_level=1.0,      # dry=100.0
                width=1.0,          # stereo=100.0
            )
        ])

        # 이펙트 체인 적용
        effected = board(audio, samplerate)

        # 결과 저장
        with AudioFile(output_path, 'w', samplerate, effected.shape[0]) as f:
            f.write(effected)
        
        print(f"[REVERB] Successfully applied reverb to {output_path}")
        return output_path
        
    except Exception as e:
        print(f"[ERROR] Failed to apply reverb: {str(e)}")
        return input_path

def convert_to_mp3(input_file, output_file):
    """wav/mp3 파일을 128kbps MP3로 변환"""
    audio = AudioSegment.from_file(input_file)
    audio.export(output_file, format='mp3', bitrate='128k')
    return output_file

def upload_to_storage(file_path, destination_path):
    """파일을 Firebase Storage에 업로드하고 URL을 반환"""
    print(f"\n[UPLOAD] Attempting to upload file:")
    print(f"[UPLOAD] Source: {file_path}")
    print(f"[UPLOAD] Destination: {destination_path}")
    
    if not os.path.exists(file_path):
        print(f"[ERROR] File not found: {file_path}")
        return None
        
    try:
        bucket = storage.bucket()
        blob = bucket.blob(destination_path)
        
        blob.upload_from_filename(
            file_path,
            content_type='audio/mpeg'
        )
        
        blob.cache_control = 'public, max-age=3600'
        blob.patch()
        
        blob.make_public()
        url = blob.public_url
        print(f"[UPLOAD] Success! URL: {url}")
        return url
    except Exception as e:
        print(f"[ERROR] Upload failed: {str(e)}")
        return None

def process_song_request(song_request_id, audio_pair_list, pitch_value):
    """API 호출"""
    url = "https://asia-northeast3-homebrew-prod.cloudfunctions.net/processSongRequest"
    payload = {
        "songRequestId": song_request_id,
        "audioPairList": audio_pair_list,
        "pitch": pitch_value

    }
    print(f"\n[API] Making request for song {song_request_id}")
    print(f"[API] Audio pairs: {json.dumps(audio_pair_list, indent=2)}")
    print(f"[API] Pitch value: {pitch_value}")
    return requests.post(url, json=payload)

def extract_number(file_path):
    file_name = os.path.basename(file_path)
    match = re.match(r"(\d+)_", file_name)
    return int(match.group(1)) if match else float("inf")

def change_pitch_sox(input_filepath, output_filepath, semitones):
    print(f"[PITCH] Changing pitch for {input_filepath}")
    tfm = sox.Transformer()
    tfm.pitch(semitones)
    tfm.build(input_filepath, output_filepath)
    print(f"[PITCH] Completed: {output_filepath}")

def process_mr_files(input_directory, output_directory, semitones, base_name):
    """MR 파일 처리 및 피치 변경"""
    mr_file = os.path.join(input_directory, f"{base_name}_mr.mp3")
    if os.path.exists(mr_file):
        if not os.path.exists(output_directory):
            os.makedirs(output_directory)
            
        output_file = os.path.join(output_directory, f"{base_name}_mr.mp3")
        if semitones != 0:
            change_pitch_sox(mr_file, output_file, semitones)
        else:
            shutil.copy(mr_file, output_file)
        
        # MP3 변환 (크기 최적화)
        optimized_output = os.path.join(output_directory, f"{base_name}_mr_optimized.mp3")
        convert_to_mp3(output_file, optimized_output)
        shutil.move(optimized_output, output_file)  # 원래 파일명으로 덮어쓰기
        
        return output_file
    return None

def get_song_name(full_path):
    return os.path.basename(full_path)


def sanitize_filename(original_name, idx):
    """
    원본 파일명에서 핵심 정보는 유지하되 문제되는 특수문자 제거
    예: '[4K⧸최초공개] 정승환 (Jung Seung Hwan) - 바람이 분다 l @JTBC K-909 221119 방송' 
    -> 'guide_1_정승환_바람이_분다'
    """
    # 1. 기본적인 특수문자 및 괄호 제거
    name = re.sub(r'[\[\]\(\)⧸\@\|\-\_\.]', ' ', original_name)
    
    # 2. 불필요한 정보 제거 (예: 화질정보, 방송정보 등)
    remove_patterns = [
        r'\d+K',           # 화질 정보 (예: 4K)
        r'최초공개',        # 부가 정보
        r'JTBC.*방송',     # 방송 정보
        r'\d{6}',         # 날짜 형식
    ]
    for pattern in remove_patterns:
        name = re.sub(pattern, '', name)
    
    # 3. 연속된 공백 제거 및 언더스코어로 변경
    name = re.sub(r'\s+', '_', name.strip())
    
    # 4. guide_{idx} 형식 추가
    return f"guide_{idx}_{name}"

if __name__ == "__main__":
    bucket = initialize_firebase()
    
    song_datas_str = sys.argv[1]
    song_datas = json.loads(song_datas_str)
    print("\n[START] Processing songs:", json.dumps(song_datas, indent=2))

    current_datetime = datetime.now().strftime('%Y%m%d-%H%M')
    download_timestamp = datetime.now().strftime('%y%m%d-%H%M')
    download_base_path = f"/content/drive/MyDrive/download/{download_timestamp}"
    
    if not os.path.exists(download_base_path):
        os.makedirs(download_base_path)

    for song_data in song_datas:
        print(f"\n{'='*50}")
        print(f"[SONG] Processing: {song_data['song_title']}")
        
        full_song_title = song_data["song_title"]
        song_title = get_song_name(full_song_title)
        voice_model = song_data["voice_model"]
        pitch_value = song_data["pitch_value"]
        isMan = song_data["isMan"]

        input_paths = find_full_path(full_song_title, isMan)
        sorted_input_paths = sorted(input_paths, key=extract_number)
        print(f"[PATH] Found {len(sorted_input_paths)} input files")

        # 디렉토리 설정
        infer_model_dir = f"/content/drive/MyDrive/infer/{voice_model}"
        infer_song_folder = f"{infer_model_dir}/[{pitch_value}]{song_title}"
        download_song_folder = os.path.join(download_base_path, voice_model, f'[{pitch_value}]{song_title}')

        for path in [infer_model_dir, infer_song_folder, download_song_folder]:
            if not os.path.exists(path):
                os.makedirs(path)

        audio_pairs = []
        
        for idx, input_path in enumerate(sorted_input_paths, 1):
            print(f"\n[PROCESS] File {idx}/{len(sorted_input_paths)}")
            
            # 파일명 생성
            original_file_name = os.path.basename(input_path)
            base_name = os.path.splitext(original_file_name)[0].replace('_vocal', '')
            
            # 보컬 처리
            voice_output_path = os.path.join(infer_song_folder, f"{base_name}_vocal.mp3")
            voice_change(
                voice_model,
                input_path,
                voice_output_path,
                pitch_value,
                f0_method="rmvpe",
                index_rate=0.66,
                filter_radius=3,
                rms_mix_rate=0.25,
                protect=0.33,
                crepe_hop_length=128,
                is_webui=0,
            )

            # 보컬 파일 최적화
            optimized_voice_path = os.path.join(infer_song_folder, f"{base_name}_vocal_optimized.mp3")
            convert_to_mp3(voice_output_path, optimized_voice_path)
            
            # 리버브 적용
            reverb_output_path = os.path.join(infer_song_folder, f"{base_name}_vocal_reverb.mp3")
            apply_reverb(optimized_voice_path, reverb_output_path)

            # MR 파일 처리
            mr_output_path = process_mr_files(
                os.path.dirname(input_path),
                infer_song_folder,
                pitch_value,
                base_name
            )

            # Storage 업로드를 위한 파일 복사
            vocal_storage_path = f"release/covers/{current_datetime}/{voice_model}/{song_title}/pitch_{pitch_value}/guide_{idx}/{sanitize_filename(base_name, idx)}_vocal.mp3"
            mr_storage_path = f"release/covers/{current_datetime}/{voice_model}/{song_title}/pitch_{pitch_value}/guide_{idx}/{sanitize_filename(base_name, idx)}_mr.mp3"

            # Storage 업로드
            vocal_url = upload_to_storage(reverb_output_path, vocal_storage_path)
            
            if mr_output_path and os.path.exists(mr_output_path):
                mr_url = upload_to_storage(mr_output_path, mr_storage_path)
                
                if vocal_url and mr_url:
                    audio_pairs.append({
                        "vocalUrl": vocal_url,
                        "mrUrl": mr_url
                    })
                    print(f"[SUCCESS] Added pair {idx}")
            else:
                print(f"[ERROR] MR file not found or processing failed")

        # API 호출
        response = process_song_request(song_data["songRequestId"], audio_pairs, song_data["pitch_value"])
        
        if response.status_code == 200:
            print(f"[API] Success: {song_data['songRequestId']}")
        else:
            print(f"[API] Error {response.status_code}: {response.text}")
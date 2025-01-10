import os
import sys
import re
import json
import sox
import shutil
from datetime import datetime
import requests
import firebase_admin
import subprocess

from firebase_admin import credentials, storage
from pydub import AudioSegment
from pedalboard import Pedalboard, Reverb, Delay, Chorus, Gain
from pedalboard.io import AudioFile
import numpy as np

from main import voice_change, find_full_path


# def normalize_to_lufs_pro(input_file, output_file, target_lufs=-14.0, target_tp=-1.0, target_lra=11.0):
#     """
#     2-Pass Loudnorm(FFmpeg)을 활용한 전문가 수준의 LUFS 정규화.
#     한글/특수문자 경로 문제 해결을 위해 임시 디렉토리 활용
#     """
#     try:
#         import uuid
#         import shutil
#         from pydub import AudioSegment
#         import json
#         import subprocess
#         import os
        
#         # 0) 임시 디렉토리 설정
#         temp_dir = "/tmp/audio_normalize"
#         os.makedirs(temp_dir, exist_ok=True)
#         temp_id = str(uuid.uuid4())[:8]
        
#         # 임시 파일 경로들 (모두 영문/숫자로만 구성)
#         temp_input = os.path.join(temp_dir, f"input_{temp_id}.mp3")
#         temp_wav_input = os.path.join(temp_dir, f"wav_input_{temp_id}.wav")
#         temp_wav_pass2 = os.path.join(temp_dir, f"wav_pass2_{temp_id}.wav")
#         temp_output = os.path.join(temp_dir, f"output_{temp_id}.mp3")
        
#         print(f"[NORMALIZE] Processing {input_file}")
#         print(f"[NORMALIZE] Using temp directory: {temp_dir}")
        
#         # 1) 입력 파일을 임시 위치로 복사
#         shutil.copy2(input_file, temp_input)
        
#         # 2) MP3를 WAV로 변환 (임시 파일)
#         audio = AudioSegment.from_file(temp_input)
#         audio.export(temp_wav_input, format='wav')
        
#         # 3) 1차 패스 - 오디오 분석
#         pass1_cmd = [
#             'ffmpeg', '-y',
#             '-i', temp_wav_input,
#             '-af', f"loudnorm=I={target_lufs}:TP={target_tp}:LRA={target_lra}:print_format=json",
#             '-f', 'null', '-',
#             '-loglevel', 'info'
#         ]
        
#         pass1_result = subprocess.run(
#             pass1_cmd,
#             stderr=subprocess.PIPE,
#             stdout=subprocess.PIPE,
#             text=True,
#             encoding='utf-8'
#         )

#         if pass1_result.returncode != 0:
#             print(f"[DEBUG] FFmpeg pass1 stderr:\n{pass1_result.stderr}")
#             raise subprocess.CalledProcessError(pass1_result.returncode, pass1_cmd)

#         # JSON 파싱 로직
#         stderr_lines = pass1_result.stderr.split('\n')
#         json_str = None
#         for line in stderr_lines:
#             if '"input_i"' in line:  # 필수 키워드로 JSON 라인 식별
#                 try:
#                     start_idx = line.find('{')
#                     end_idx = line.rfind('}') + 1
#                     if start_idx != -1 and end_idx != -1:
#                         json_str = line[start_idx:end_idx]
#                         break
#                 except:
#                     continue

#         if not json_str:
#             print("[WARNING] JSON parsing failed, using default normalization values")
#             measured_data = {
#                 "input_i": -27.0,
#                 "input_tp": -2.0,
#                 "input_lra": 15.0,
#                 "input_thresh": -38.0,
#                 "target_offset": 0.0
#             }
#         else:
#             try:
#                 measured_data = json.loads(json_str)
#                 print(f"[DEBUG] Parsed loudnorm data: {measured_data}")
#             except json.JSONDecodeError as je:
#                 print(f"[WARNING] JSON decode error: {je}, using default values")
#                 measured_data = {
#                     "input_i": -27.0,
#                     "input_tp": -2.0,
#                     "input_lra": 15.0,
#                     "input_thresh": -38.0,
#                     "target_offset": 0.0
#                 }

#         # 4) 2차 패스 - 정규화 적용
#         loudnorm_filter = (
#             f"loudnorm=I={target_lufs}:TP={target_tp}:LRA={target_lra}"
#             f":measured_I={measured_data['input_i']}"
#             f":measured_TP={measured_data['input_tp']}"
#             f":measured_LRA={measured_data['input_lra']}"
#             f":measured_thresh={measured_data['input_thresh']}"
#             f":offset={measured_data['target_offset']}"
#             ":linear=true:print_format=json"
#         )

#         pass2_cmd = [
#             'ffmpeg', '-y',
#             '-i', temp_wav_input,
#             '-af', loudnorm_filter,
#             '-ar', '48000',
#             '-c:a', 'pcm_s24le',
#             temp_wav_pass2
#         ]
        
#         subprocess.run(pass2_cmd, check=True)

#         # 5) 정규화된 WAV를 MP3로 변환
#         final_audio = AudioSegment.from_wav(temp_wav_pass2)
#         final_audio.export(temp_output, format='mp3', bitrate='320k')

#         # 6) 최종 결과물을 목적 경로로 복사
#         shutil.copy2(temp_output, output_file)

#         # 7) 임시 파일들 정리
#         temp_files = [temp_input, temp_wav_input, temp_wav_pass2, temp_output]
#         for tmp in temp_files:
#             try:
#                 if os.path.exists(tmp):
#                     os.remove(tmp)
#             except Exception as e:
#                 print(f"[WARNING] Failed to remove temp file {tmp}: {str(e)}")
        
#         print(f"[NORMALIZE] Successfully normalized to {target_lufs} LUFS: {output_file}")
#         return True

#     except Exception as e:
#         print(f"[ERROR] During normalization: {str(e)}")
#         print("[FALLBACK] Attempting simple normalization...")
#         try:
#             # 간단한 RMS 기반 정규화로 폴백
#             audio = AudioSegment.from_file(input_file)
#             target_dbfs = -14.0  # Approximately -14 LUFS
#             change_in_dbfs = target_dbfs - audio.dBFS
#             normalized_audio = audio.apply_gain(change_in_dbfs)
#             normalized_audio.export(output_file, format='mp3', bitrate='320k')
#             print("[FALLBACK] Simple normalization completed")
#             return True
#         except Exception as fallback_error:
#             print(f"[ERROR] Fallback normalization also failed: {str(fallback_error)}")
#             print("[FALLBACK] Copying original file as fallback...")
#             try:
#                 # 최후의 수단: 원본 파일 복사
#                 shutil.copy2(input_file, output_file)
#                 print("[FALLBACK] Original file copied as fallback")
#                 return True
#             except Exception as copy_error:
#                 print(f"[FATAL] All normalization attempts failed: {str(copy_error)}")
#                 return False


def normalize_to_lufs_pro(input_file, output_file, target_lufs=-14.0, target_tp=-1.0, target_lra=11.0):
    """
    Bypass normalization - simply copy the input file to the output file
    """
    try:
        import shutil
        print(f"[NORMALIZE] Bypassing normalization for {input_file}")
        
        # Simply copy the input file to the output file
        shutil.copy2(input_file, output_file)
        
        print(f"[NORMALIZE] File copied as-is: {output_file}")
        return True

    except Exception as e:
        print(f"[ERROR] During file copy: {str(e)}")
        return False


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


def sanitize_filename(base_name, idx):
    """파일명 단순화"""
    # 특수문자 제거하고 간단하게 변경
    return f"guide_{idx}_vocal"


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

            # LUFS 정규화 적용 (보컬)
            normalized_vocal_path = os.path.join(infer_song_folder, f"{base_name}_vocal_normalized.mp3")
            if not normalize_to_lufs_pro(reverb_output_path, normalized_vocal_path, target_lufs=-14.0, target_tp=-1.0, target_lra=11.0):
                print("[ERROR] Vocal normalization failed, using non-normalized file")
                normalized_vocal_path = reverb_output_path

            # MR 파일 처리
            mr_output_path = process_mr_files(
                os.path.dirname(input_path),
                infer_song_folder,
                pitch_value,
                base_name
            )

            if mr_output_path and os.path.exists(mr_output_path):
                # LUFS 정규화 적용 (MR)
                normalized_mr_path = os.path.join(infer_song_folder, f"{base_name}_mr_normalized.mp3")
                if not normalize_to_lufs_pro(mr_output_path, normalized_mr_path, target_lufs=-14.0, target_tp=-1.0, target_lra=11.0):
                    print("[ERROR] MR normalization failed, using non-normalized file")
                    normalized_mr_path = mr_output_path
                mr_output_path = normalized_mr_path

            # Storage 업로드를 위한 파일 복사
            vocal_storage_path = f"release/covers/{current_datetime}/{voice_model}/{song_title}/pitch_{pitch_value}/guide_{idx}/{sanitize_filename(base_name, idx)}_vocal.mp3"
            mr_storage_path = f"release/covers/{current_datetime}/{voice_model}/{song_title}/pitch_{pitch_value}/guide_{idx}/{sanitize_filename(base_name, idx)}_mr.mp3"

            # Storage 업로드
            vocal_url = upload_to_storage(normalized_vocal_path, vocal_storage_path)
            
            if mr_output_path and os.path.exists(mr_output_path):
                mr_url = upload_to_storage(mr_output_path, mr_storage_path)
                
                if vocal_url and mr_url:
                    audio_pairs.append({
                        "vocalUrl": vocal_url,
                        "mrUrl": mr_url,
                        "pitch": pitch_value
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
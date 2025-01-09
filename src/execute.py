# execute.py
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

from main import voice_change, find_full_path

def initialize_firebase():
    """Firebase Storage 초기화"""
    if not firebase_admin._apps:
        cred = credentials.Certificate('/content/credentials.release.json')
        firebase_admin.initialize_app(cred, {
            'storageBucket': 'homebrew-prod.appspot.com'
        })
    return storage.bucket()

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

def process_song_request(song_request_id, audio_pair_list):
    """API 호출"""
    url = "https://asia-northeast3-homebrew-prod.cloudfunctions.net/processSongRequest"
    payload = {
        "songRequestId": song_request_id,
        "audioPairList": audio_pair_list
    }
    print(f"\n[API] Making request for song {song_request_id}")
    print(f"[API] Audio pairs: {json.dumps(audio_pair_list, indent=2)}")
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

def process_mp3_files(input_directory, output_directory, semitones, file_endings):
    print(f"\n[MR] Processing MP3 files in {input_directory}")
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)
        print(f"[MR] Created directory: {output_directory}")

    for filename in os.listdir(input_directory):
        if any(filename.endswith(ending) for ending in file_endings):
            input_filepath = os.path.join(input_directory, filename)
            output_filepath = os.path.join(output_directory, filename)
            change_pitch_sox(input_filepath, output_filepath, semitones)
            print(f"[MR] Processed {filename}")

def get_song_name(full_path):
    return os.path.basename(full_path)

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
        for path in sorted_input_paths:
            print(f"[PATH] - {path}")

        # 디렉토리 설정
        infer_model_dir = f"/content/drive/MyDrive/infer/{voice_model}"
        infer_song_folder = f"{infer_model_dir}/[{pitch_value}]{song_title}"
        download_song_folder = os.path.join(download_base_path, voice_model, f'[{pitch_value}]{song_title}')

        for path in [infer_model_dir, infer_song_folder, download_song_folder]:
            if not os.path.exists(path):
                os.makedirs(path)
                print(f"[DIR] Created: {path}")

        audio_pairs = []
        
        for idx, input_path in enumerate(sorted_input_paths, 1):
            print(f"\n[PROCESS] File {idx}/{len(sorted_input_paths)}")
            print(f"[PROCESS] Input: {input_path}")
            
            original_file_name = os.path.basename(input_path)
            base_name = os.path.splitext(original_file_name)[0].replace('_vocal', '')
            print(f"[FILE] Original: {original_file_name}")
            print(f"[FILE] Base name: {base_name}")
            
            # Voice change
            output_path = os.path.join(infer_song_folder, f"{original_file_name}.mp3")
            voice_change(
                voice_model, input_path, output_path, pitch_value,
                f0_method="rmvpe", index_rate=0.66, filter_radius=3,
                rms_mix_rate=0.25, protect=0.33, crepe_hop_length=128,
                is_webui=0,
            )

            # MR 파일 처리
            input_dir = os.path.dirname(input_path)
            mr_file_name = f"{base_name}_mr.mp3"
            original_mr_path = os.path.join(input_dir, mr_file_name)
            
            print(f"\n[MR] Checking MR file:")
            print(f"[MR] Expected path: {original_mr_path}")
            print(f"[MR] Exists: {os.path.exists(original_mr_path)}")

            final_mr_path = original_mr_path
            if pitch_value != 0 and os.path.exists(original_mr_path):
                print(f"[MR] Pitch change needed ({pitch_value})")
                mr_output_path = os.path.join(infer_song_folder, 'mr')
                process_mp3_files(
                    input_dir, mr_output_path, pitch_value,
                    ['_mr.mp3', '_corus.mp3']
                )
                final_mr_path = os.path.join(mr_output_path, mr_file_name)
                print(f"[MR] Pitch-changed path: {final_mr_path}")

            # Storage 업로드
            dst_output_path = os.path.join(download_song_folder, f"{original_file_name}.mp3")
            shutil.copy(output_path, dst_output_path)
            print(f"[FILE] Copied to: {dst_output_path}")

            # Storage 경로 설정 및 업로드
            storage_base_path = f"release/covers/{current_datetime}/{voice_model}/{song_title}/pitch_{pitch_value}/guide_{idx}"
            
            vocal_storage_path = f"{storage_base_path}/vocal.mp3"
            vocal_url = upload_to_storage(dst_output_path, vocal_storage_path)
            
            # MR 파일 업로드 시도
            if os.path.exists(final_mr_path):
                mr_storage_path = f"{storage_base_path}/mr.mp3"
                mr_url = upload_to_storage(final_mr_path, mr_storage_path)
                
                if vocal_url and mr_url:
                    audio_pairs.append({
                        "vocalUrl": vocal_url,
                        "mrUrl": mr_url
                    })
                    print(f"[SUCCESS] Added pair {idx}")
            else:
                print(f"[ERROR] MR file not found: {final_mr_path}")

        # API 호출
        response = process_song_request(song_data["songRequestId"], audio_pairs)
        
        if response.status_code == 200:
            print(f"[API] Success: {song_data['songRequestId']}")
        else:
            print(f"[API] Error {response.status_code}: {response.text}")
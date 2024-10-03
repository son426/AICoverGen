import os
import sys
import re
import json
import sox
import shutil
from datetime import datetime

from main import voice_change, find_full_path

# 파일 경로에서 1_,2_ 를 추출하는 함수
def extract_number(file_path):
    file_name = os.path.basename(file_path)
    match = re.match(r"(\d+)_", file_name)
    return int(match.group(1)) if match else float("inf")

def change_pitch_sox(input_filepath, output_filepath, semitones):
    tfm = sox.Transformer()
    tfm.pitch(semitones)
    tfm.build(input_filepath, output_filepath)

def process_mp3_files(input_directory, output_directory, semitones, file_endings):
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    for filename in os.listdir(input_directory):
        if any(filename.endswith(ending) for ending in file_endings):
            input_filepath = os.path.join(input_directory, filename)
            output_filepath = os.path.join(output_directory, filename)
            change_pitch_sox(input_filepath, output_filepath, semitones)
            print(f"{filename}의 피치가 {semitones} 반음만큼 변경되었습니다.")

if __name__ == "__main__":
    song_datas_str = sys.argv[1]  # 첫 번째 인자
    song_datas = json.loads(song_datas_str)
    print(song_datas)

    # 현재 날짜와 시간을 기반으로 다운로드 폴더 생성
    current_datetime = datetime.now().strftime('%y%m%d-%H%M')
    download_base_path = f"/content/drive/MyDrive/download/{current_datetime}"
    if not os.path.exists(download_base_path):
        os.makedirs(download_base_path)

    for song_data in song_datas:
        song_title = song_data["song_title"]
        voice_model = song_data["voice_model"]
        pitch_value = song_data["pitch_value"]
        isMan = song_data["isMan"]

        input_paths = find_full_path(song_title, isMan)
        sorted_input_paths = sorted(input_paths, key=extract_number)

        # 기존 infer 폴더에 필요한 디렉토리 생성
        if not os.path.exists(f"/content/drive/MyDrive/infer/{voice_model}"):
            os.mkdir(f"/content/drive/MyDrive/infer/{voice_model}")
        infer_song_folder = f"/content/drive/MyDrive/infer/{voice_model}/[{pitch_value}]{song_title}"
        if not os.path.exists(infer_song_folder):
            os.mkdir(infer_song_folder)

        # 다운로드 폴더 내에 해당 폴더 생성
        download_song_folder = os.path.join(download_base_path, voice_model, f'[{pitch_value}]{song_title}')
        if not os.path.exists(download_song_folder):
            os.makedirs(download_song_folder)

        for input_path in sorted_input_paths:
            file_name = os.path.basename(input_path)
            output_path = os.path.join(infer_song_folder, f"{file_name}.mp3")
            voice_change(
                voice_model,
                input_path,
                output_path,
                pitch_value,
                f0_method="rmvpe",
                index_rate=0.66,
                filter_radius=3,
                rms_mix_rate=0.25,
                protect=0.33,
                crepe_hop_length=128,
                is_webui=0,
            )

            # 피치 조정이 필요한 경우
            if pitch_value != 0:
                mr_input_path = os.path.dirname(input_path)
                mr_output_path = os.path.join(infer_song_folder, 'mr')
                process_mp3_files(
                    mr_input_path, mr_output_path, pitch_value, ['_mr.mp3', '_corus.mp3']
                )
            else:
                # 피치 변경이 필요 없을 경우 mr 및 corus 파일을 복사
                mr_input_path = os.path.dirname(input_path)
                mr_output_path = os.path.join(infer_song_folder, 'mr')
                if not os.path.exists(mr_output_path):
                    os.makedirs(mr_output_path)
                for filename in os.listdir(mr_input_path):
                    if filename.endswith('_mr.mp3') or filename.endswith('_corus.mp3'):
                        src_file = os.path.join(mr_input_path, filename)
                        dst_file = os.path.join(mr_output_path, filename)
                        shutil.copy(src_file, dst_file)
                        print(f"{filename} 파일을 복사했습니다.")

            # 처리된 파일을 다운로드 폴더에 복사
            # 보이스 체인지된 오디오 파일 복사
            dst_output_path = os.path.join(download_song_folder, f"{file_name}.mp3")
            shutil.copy(output_path, dst_output_path)

            # mr 및 corus 파일 복사
            mr_output_path = os.path.join(infer_song_folder, 'mr')
            if os.path.exists(mr_output_path):
                dst_mr_output_path = os.path.join(download_song_folder, 'mr')
                if not os.path.exists(dst_mr_output_path):
                    os.makedirs(dst_mr_output_path)
                for filename in os.listdir(mr_output_path):
                    src_file = os.path.join(mr_output_path, filename)
                    dst_file = os.path.join(dst_mr_output_path, filename)
                    shutil.copy(src_file, dst_file)

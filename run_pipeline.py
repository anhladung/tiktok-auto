import subprocess
import sys
import os
import time


BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)


def run_script(name, filename):

    print("=" * 70)
    print("START:", name)
    print("=" * 70)


    path = os.path.join(
        BASE_DIR,
        filename
    )


    if not os.path.exists(path):
        print("MISSING:", filename)
        return False


    result = subprocess.run(
        [
            sys.executable,
            path
        ]
    )


    if result.returncode != 0:
        print("FAILED:", name)
        return False


    print("FINISHED:", name)

    time.sleep(2)

    return True



def main():


    pipeline = [

        # IMAGE
        #(
        #    "Build Image Queue",
        #    "build_image_queue_1.py"
        #),

        (
            "Image Worker",
            "image_worker_1.py"
        ),


        # SCRIPT
        #(
        #    "Build Script Queue",
        #    "build_script_queue.py"
        #),

        #(
        #    "Script Worker",
        #    "script_worker_1.py"
        #),


        # RENDER
        (
            "Build Render Queue",
            "build_render_queue_1.py"
        ),

        (
            "Render Worker",
            "render_worker_2.py"
        ),


        # VOICE
        #(
        #    "Build Voice Queue",
        #    "build_voice_queue.py"
        #),

        #(
        #    "Voice Worker",
        #    "voice_worker.py"
        #),


        # AUDIO
        #(
        #    "Audio Planner",
        #    "audio_planner.py"
        #),


        # FINAL VIDEO
        (
            "Build Final Video",
            "build_final_video.py"
        ),


        # UPLOAD
        #(
        #    "Build Upload Queue",
        #    "build_upload_queue.py"
        #),


        #(
        #    "Build Facebook Queue",
        #    "build_facebook_queue.py"
        #),


        #(
        #    "Build Threads Queue",
        #   "build_threads_queue.py"
        #),


        #(
        #    "Build TikTok Schedule",
        #    "build_tiktok_schedule.py"
        #),

        #(
        #    "Build Facebook Schedule",
        #    "build_facebook_schedule.py"
        #),


        #(
        #    "Build Threads Schedule",
        #    "build_threads_schedule.py"
        #),


        #(
        #    "Facebook Upload Worker",
        #    "facebook_upload_worker.py"
        #),

        #(
        #    "Threads Upload Worker",
        #    "threads_upload_worker.py"
        #),

        #(
        #    "TikTok Upload Worker",
        #    "tiktok_upload_worker.py"
        #)

    ]


    for name, file in pipeline:

        success = run_script(
            name,
            file
        )


        if not success:
            print("\nPIPELINE STOPPED")
            break



if __name__ == "__main__":
    main()
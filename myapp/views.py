import os
import time
import subprocess
import requests
from django.shortcuts import render
import pytz
from datetime import datetime
from myproject.settings import MEDIA_ROOT,MEDIA_URL,BASE_DIR


# Hugging Face API settings
HF_API_TOKEN = "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"
HEADERS = {"Authorization": f"Bearer {HF_API_TOKEN}"}

context = {}
now = ""
save_dir = ""
save_dir_abs = ""

def generate_scenes(script):
    api_url = "https://api-inference.huggingface.co/models/facebook/bart-large-cnn"
    data = {"inputs": script, "parameters": {"max_length": 400, "do_sample": True, "temperature": 0.7, "top_p": 0.95}}
    response = requests.post(api_url, headers=HEADERS, json=data)
    response_data = response.json()

    try:
        return [
            scene.strip()
            for scene in response_data[0]["summary_text"].split(".")
            if scene.strip()
        ]
    except (KeyError, IndexError):
        return []

def generate_images(scenes, template, save_dir):
    api_url = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-dev"
    generated_images = []
    err_limit,total_frame_cnt,scene_frame_cnt=0,0,0
    for i, description in enumerate(scenes):
        # Make API request
        while True:
            if err_limit==5 or scene_frame_cnt==3:
                err_limit,scene_frame_cnt=0,0
                break
            else:
                data = {
                "inputs": description+" "+template[scene_frame_cnt],
                "parameters": {
                    "width": 512,
                    "height": 512,
                    "seed":42,
                    "num_inference_steps": 25,
                    "guidance_scale": 7.5,
                }
                }
                response = requests.post(api_url, headers=HEADERS, json=data)
                if response.status_code == 200:
                    with open(f"{total_frame_cnt+1:04d}.png", "wb") as frame:
                        frame.write(response.content)
                    img = os.path.join(save_dir,f"{total_frame_cnt+1:04d}.png").replace("\\\\", "/").replace("\\", "/")
                    generated_images.append(img)
                    scene_frame_cnt+=1
                    total_frame_cnt+=1
                    time.sleep(5)
                else:
                    time.sleep(5)
                    err_limit+=1
        time.sleep(5)
    return generated_images

def interpolated_images(save_dir):
    os.chdir(os.path.dirname(save_dir))
    cmd = [
        "python",
        os.path.join(BASE_DIR,"ECCV2022-RIFE","inference_video.py").replace("\\\\", "/").replace("\\", "/"),
        "--exp=5",
        f"--img={save_dir}",
        "--model",
        os.path.join(BASE_DIR,"ECCV2022-RIFE","train_log").replace("\\\\", "/").replace("\\", "/")
    ]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        return False
    return True

def create_video(image_paths):
    global now
    os.chdir(image_paths)
    cmd = [
        "ffmpeg",
        "-framerate",
        "32",
        "-i",
        "%07d.png",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        os.path.join(os.path.dirname(image_paths),f"{now}.mp4").replace("\\\\", "/").replace("\\", "/"),
        "-y"
    ]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        return False
    return True

def home(request):
    global context
    context = {}
    if request.method == "POST":
        # channel_layer = get_channel_layer()

        script = request.POST.get("script", "").strip()
        if not script:
            context["error"] = "Script is required."
            return render(request, 'home.html', context)
        elif len(script) < 30:
            context["error"] = "Script is too short."
            return render(request, 'home.html', context)

        # Step 1: Generate scenes
        scenes = generate_scenes(script)

        if not scenes:
            context["error"] = "Error in generating scenes"
            return render(request, 'home.html', context)
        
        context["scenes"] = scenes

        return render(request,"scenes.html",context)
    return render(request, 'home.html', context)
    
def key_frames(request):
    if request.method == "POST":
        global context, save_dir, save_dir_abs

        timezone = pytz.timezone("Asia/Kolkata")
        now = datetime.now(timezone).strftime("%d-%m--%H-%M")
        save_dir = os.path.join(MEDIA_URL, f"script-{now}", "images").replace("\\\\", "/").replace("\\", "/")
        save_dir_abs = os.path.join(MEDIA_ROOT, f"script-{now}", "images").replace("\\\\", "/").replace("\\", "/")
        os.makedirs(save_dir_abs, exist_ok=True)
        os.chdir(save_dir_abs)

        # Step 2: Generate images
        angles = ["front view realistic", "45 degree left front view realistic", "90 degree left side view realistic", ""]
        images = generate_images(context["scenes"], angles, save_dir)

        if not images:
            context["error"] = "Key frames not generated"
            return render(request, 'home.html', context)
        
        context["keyframes"] = images

        return render(request, 'keyframes.html', context)

    return render(request, 'home.html', context)

def interpolated_frames(request):
    if request.method == "POST":
        global context, save_dir_abs
        # Step 3: Generate intermediate images
        if not interpolated_images(save_dir_abs):

            context["error"] = "Error in interpolated frames"
            return render(request, 'home.html', context)

        context["interpolated"] = True
        return render(request, 'interpolated.html', context)

    return render(request, 'home.html', context)
    
def video(request):
    if request.method == "POST":
        global context, save_dir, save_dir_abs, now
        # Step 4: Create video
        if not create_video(os.path.join(os.path.dirname(save_dir_abs), "vid_out").replace("\\\\", "/").replace("\\", "/")):

            context["error"] = "Video generation error"
            return render(request, "home.html", context)

        video_path = os.path.join(os.path.dirname(save_dir), f"{now}.mp4").replace("\\\\", "/").replace("\\", "/")
        context["video_url"] = video_path
        return render(request, "video.html", context)
    
    return render(request, 'home.html', context)
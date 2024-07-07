import os
import cv2
import torch
import numpy as np
from ultralytics import YOLO
from dotenv import load_dotenv
from openai import OpenAI
import base64
import pickle

from extract_video_highlight import extract_hightlight
from gen_score_change_summary import gen_score_change_summary

load_dotenv()
API_KEY = os.getenv("API_KEY")
client = OpenAI(api_key=API_KEY)

MODEL="gpt-4o"

# Open the image file and encode it as a base64 string
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def ask_question(first_base64_image, second_base64_image):
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant that reponds with either TRUE or FALSE. The user will provide two scoreboards from a baseball game in different time. Please tell the user if the scores of the game in the first image and the second image are the same. Return TRUE if the scores are the same, and FALSE if the scores are different."},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {
                    "url": f"data:image/png;base64,{first_base64_image}"}
                },
                {"type": "image_url", "image_url": {
                    "url": f"data:image/png;base64,{second_base64_image}"}
                }
            ]}
        ],
        temperature=0.7,
    )
    # print(response.choices[0].message.content)
    return response.choices[0].message.content.lower() == "true"


ckpt_file = "soccer_scoreboard.pt"
video_file = "./Decibels/videos/soccer-full.mp4"
tmp_frames_dir = "./frames_tmp"

yolo_model = YOLO(ckpt_file)
video = cv2.VideoCapture(video_file)
fps = video.get(cv2.CAP_PROP_FPS)
if os.path.exists(tmp_frames_dir):
    os.system("rm -r {}".format(tmp_frames_dir))
os.mkdir(tmp_frames_dir)

def writeImage(image, file_dir, currentIdx):
    if (currentIdx < 10):
        output_num = "000" + str(currentIdx)
    elif (currentIdx < 100):
        output_num = "00" + str(currentIdx)
    elif (currentIdx < 1000):
        output_num = "0" + str(currentIdx)
    else:
        output_num = str(currentIdx)
    img_file = file_dir + "/" + str(output_num) + ".jpg"
    cv2.imwrite(img_file, image)

## extract frames
count = 1
current_idx = 1
sec = 30
success, image = video.read()
while success:
    if count > (fps*current_idx*sec):
        writeImage(image, tmp_frames_dir, current_idx)
        current_idx += 1
    success, image = video.read()
    count += 1

## scoreboard detection
frames_dir = "./frames"
os.system("rm -r {}".format(frames_dir))
os.mkdir(frames_dir)
low, high = 0, 0
scoreboard_pos = []
frames = sorted(os.listdir(tmp_frames_dir))
for i in range(len(frames)):
    target_img = tmp_frames_dir + "/" + frames[i]
    detect_result = yolo_model.predict(source=target_img, conf=0.5, verbose=False)
    classes = torch.Tensor.numpy(detect_result[0].boxes.xyxy.cpu())
    confidence = torch.Tensor.numpy(detect_result[0].boxes.conf.cpu())
    if (len(classes) > 0):
        os.system("mv {tmp} {out}".format(
            tmp=target_img,
            out=frames_dir
        ))
        scoreboard_pos.append(np.ndarray.tolist(classes[np.argmax(confidence)]))
os.system("rm -r {}".format(tmp_frames_dir))

# backward order and check every frame to find the first frame with scoreboard
video = cv2.VideoCapture(video_file)
fps = video.get(cv2.CAP_PROP_FPS)
cnt = video.get(cv2.CAP_PROP_FRAME_COUNT)
# from the last frame
while cnt > 0:
    print(cnt, flush=True)
    cnt -= int(fps)
    video.set(cv2.CAP_PROP_POS_FRAMES, cnt)
    success, image = video.read()
    if not success:
        continue
    detect_result = yolo_model.predict(source=image, conf=0.5, verbose=False)
    classes = torch.Tensor.numpy(detect_result[0].boxes.xyxy.cpu())
    confidence = torch.Tensor.numpy(detect_result[0].boxes.conf.cpu())
    if (len(classes) > 0):
        writeImage(image, frames_dir, int(cnt//fps)//sec)
        scoreboard_pos.append(np.ndarray.tolist(classes[np.argmax(confidence)]))
        break

frames = sorted(os.listdir(frames_dir))

## ask LLM
def askLLM(target, ref):
    os.system("rm -r ./scoreboard")
    os.mkdir("./scoreboard")
    target_file = frames_dir + "/" + frames[target]
    ref_file = frames_dir + "/" + frames[ref]

    # crop scoreboard
    target_img = cv2.imread(target_file)
    ref_img = cv2.imread(ref_file)
    cropped_target = target_img[int(scoreboard_pos[target][1]):int(scoreboard_pos[target][3]), int(scoreboard_pos[target][0]):int(scoreboard_pos[target][2])]
    cropped_ref = ref_img[int(scoreboard_pos[ref][1]):int(scoreboard_pos[ref][3]), int(scoreboard_pos[ref][0]):int(scoreboard_pos[ref][2])]
    cropped_target_file = "./scoreboard/target.jpg"
    cropped_ref_file = "./scoreboard/ref.jpg"
    cv2.imwrite(cropped_target_file, cropped_target)
    cv2.imwrite(cropped_ref_file, cropped_ref)

    # LLM
    encoded_target = encode_image(cropped_target_file)
    encoded_ref = encode_image(cropped_ref_file)
    response = ask_question(encoded_ref, encoded_target)

    # the output should be "True" or "False"
    print(f"askLLM ({target} -> {ref}): {response}")
    return response

def binarySearch(low, high, highlight_idx):
    if low == high:
        return
    if low == high - 1:
        highlight_idx.append(low)
        return
    mid = (low + high) // 2
    answer_l = askLLM(low, mid)
    answer_r = askLLM(mid, high)
    
    if not answer_l: # Different
        binarySearch(low, mid, highlight_idx)
    if not answer_r: # Different
        binarySearch(mid, high, highlight_idx)

if os.path.exists("highlight_idx.pkl"):
    with open("highlight_idx.pkl", "rb") as f:
        highlight_idx = pickle.load(f)
else:
    highlight_idx = []
    binarySearch(0, len(frames)-1, highlight_idx)
    if highlight_idx[-1] != len(frames) - 1:
        highlight_idx.append(len(frames) - 1)
    with open("highlight_idx.pkl", "wb") as f:
        pickle.dump(highlight_idx, f)

print(highlight_idx)

# read the scoreboard from highlight_idx and get the score and innings information
if os.path.exists("highlight_scoreboard.pkl") and os.path.exists("highlight_innings.pkl"):
    with open("highlight_scoreboard.pkl", "rb") as f:
        scoreboard = pickle.load(f)
    with open("highlight_innings.pkl", "rb") as f:
        innings = pickle.load(f)
else:
    scoreboard = []
    innings = []
    for i in highlight_idx:
        target_file = frames_dir + "/" + frames[i]
        target_img = cv2.imread(target_file)
        cropped_target = target_img[int(scoreboard_pos[i][1]):int(scoreboard_pos[i][3]), int(scoreboard_pos[i][0]):int(scoreboard_pos[i][2])]
        cropped_target_file = "./scoreboard/target.jpg"
        cv2.imwrite(cropped_target_file, cropped_target)
        encoded_target = encode_image(cropped_target_file)
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that reponds with the score and innings of a baseball game. The user will provide a scoreboard from a baseball game. Please tell the user the score and innings of the game in the image. Answer in the format of 'SCORE: [x-x], INNINGS: [x]' (x should be a number only, if innings are not available, set it to 9) ."},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/png;base64,{encoded_target}"}
                    }
                ]}
            ],
            temperature=0.7,
        )
        # parse the response
        response = response.choices[0].message.content
        print(response)
        response = response.split("SCORE: ")[1]
        score, inning = response.split(", INNINGS: ")
        print(score, inning)
        scoreboard.append(score)
        innings.append(inning)

    with open("highlight_scoreboard.pkl", "wb") as f:
        pickle.dump(scoreboard, f)

    with open("highlight_innings.pkl", "wb") as f:
        pickle.dump(innings, f)

print(scoreboard)
print(innings)

fps = video.get(cv2.CAP_PROP_FPS)
frame_cnt = video.get(cv2.CAP_PROP_FRAME_COUNT)
_, highlight_secs = gen_score_change_summary(highlight_idx, scoreboard, innings, frame_cnt, fps, sec, frames_dir)

extract_hightlight(video_file, highlight_secs)
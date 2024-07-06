from openai import OpenAI
from dotenv import load_dotenv
from pydub import AudioSegment
import csv
import argparse


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("text", type=str, help="input transcript")
    parser.add_argument("-o", "--output", type=str, help="output summary file")
    args = parser.parse_args()
    
    load_dotenv()
    client = OpenAI()
    
    transcripts = []
    # PyDub handles time in millisecon
    with open(args.text) as f:
        reader = csv.DictReader(f)
        for row in reader:
            transcripts.append(row)
            
    # MESSAGE_CONTENT = "請分析以下逐字稿，並且切出「適當」的時間軸，以表格形式呈現相對應的摘要，並且與分數變化高度相關，在最後也給出您推薦的本場賽事精華的時間點(3~10個)。"
    MESSAGE_CONTENT = """Please analyze the following transcript about a baseball game. 
    Please split out appropriate and correct timelines and present the corresponding summary in table format, highly correlated with the change of scores.
    At last, please also recommend 3~10 highlight timelines of this baseball game."""

    MESSAGES = [
        # {"role": "system", "content": "你是一個得力的助手，並且可以對給定的逐字稿(有對應的時間)做出高品質的摘要。"},
        {"role": "system", "content": "You are a helpful assistant and is able to produce high-quality summary for the given transcript with timestamps."},
        {"role": "user", "content": f"{MESSAGE_CONTENT}\n{', '.join([str(t) for t in transcripts])}"},
    ]

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=MESSAGES,
        temperature=0.4,
    )

    file_name = "generated_summary.md"
    if args.output:
        file_name = args.output

    # Save the text to the file
    with open(file_name, 'w') as file:
        file.write(response.choices[0].message.content)

    print(f"Generated text saved to {file_name}")


    


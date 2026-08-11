import whisper


print("Loading Whisper model...")


# 加载模型
model = whisper.load_model("base")


print("Model loaded!")


# 自动检测语言
result = model.transcribe(
    "test.wav",
    fp16=False
)


language_map = {
    "en": "English",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "fr": "French"
}


lang = result["language"]


print(
    "\n检测语言:",
    language_map.get(lang, lang)
)


print("\n识别结果:")
print(result["text"])


print("\n时间轴:")
for segment in result["segments"]:
    print(
        f"{segment['start']:.2f}s --> {segment['end']:.2f}s"
    )
    print(segment["text"])
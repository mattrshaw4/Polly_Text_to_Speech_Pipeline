import boto3

with open('speech.txt', 'r') as file:
    text = file.read()
    print(text)


    polly = boto3.client('polly')

    response = polly.synthesize_speech(
        Engine ="generative",
        OutputFormat=": "mp3",
        "Text": text,
        "VoiceId": "Stephen"
    )


    audio_stream = response['AudioStream']


    with open('example.mp3', 'wb') as f:
        f.write(audio_stream.read())
        print("Polly output saved.")




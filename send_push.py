import requests
import os
from dotenv import load_dotenv

# Läs in variabler från .env-filen
load_dotenv()
    
GOTIFY_URL = "http://localhost/message?token=AhWUuzjG9Pi92Oi"
PUSHOVER_URL = "https://api.pushover.net/1/messages.json"
PUSHOVER_USER = os.getenv("PUSHOVER_USER")
PUSHOVER_TOKEN = os.getenv("PUSHOVER_TOKEN")


def send_push(title , message, priority = 3):
    data = {}
    data['user'] = PUSHOVER_USER
    data['token'] = PUSHOVER_TOKEN
    data['title']=title
    data['message']=message
    #data['priority']=priority
    data['sound']='vibrate'
    return requests.post(PUSHOVER_URL,data)
    
if __name__ == "__main__":
   
    print(send_push("test", "hello world"))
    
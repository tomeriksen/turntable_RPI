from flask import Flask
import os

app = Flask(__name__)

TOGGLE_STATE_FILE = /tmp/toggle-audio-state
SINK_LINEOUT = "alsa_output.platform-bcm2835_audio.stereo-fallback"
SINK_HOMEPOD = "raop_sink.Vardagsrum.local.10.0.1.22.7000"

def toggle_audio():
    if not os.path.exist(TOGGLE_STATE_FILE):
        #crete file
        with open(TOGGLE_STATE_FILE,"w") as f:
            f.write(SINK_LINEOUT)
    
    with open(TOGGLE_STATE_FILE, "r") as r:
        current_output = f.read().strip()
    
    sink_inputs = os.popen("pactl list sink-inputs short | awk '{print $1}'").read().split()

    if current_output == "lineout":
        #move input
        for input_id in sink_inputs:
            os.system(f"pactl move-sink-input {input_id} {SINK_HOMEPOD}")
        with open(TOGGLE_STATE_FILE, "w") as f:
            f.write("homepod")
        



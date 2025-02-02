from flask import Flask, render_template, request
import os

app = Flask(__name__)

TOGGLE_STATE_FILE = "/tmp/toggle-audio-state"
SINK_LINEOUT = "alsa_output.platform-bcm2835_audio.stereo-fallback"
SINK_HOMEPOD = "raop_sink.Vardagsrum.local.10.0.1.22.7000"

def open_toggle_state_file(write=False):
    #check if file exists
    if not os.path.exists(TOGGLE_STATE_FILE):
        #create
        with open(TOGGLE_STATE_FILE,"w") as f:
            f.write(SINK_LINEOUT)

    if write:
        return open(TOGGLE_STATE_FILE, "w")
    else:
        return open(TOGGLE_STATE_FILE, "r")
    
    
def toggle_audio():
    if not os.path.exists(TOGGLE_STATE_FILE):
        #create file
        with open(TOGGLE_STATE_FILE,"w") as f:
            f.write(SINK_LINEOUT)
    
    with open(TOGGLE_STATE_FILE,"r") as f:
        current_output = f.read().strip()
    
    sink_inputs = os.popen("pactl list sink-inputs short | awk '{print $1}'").read().split()

    if current_output == "lineout":
        #move input
        for input_id in sink_inputs:
            os.system(f"pactl move-sink-input {input_id} {SINK_HOMEPOD}")
        with open_toggle_state_file("w") as f:
            f.write("homepod")
        
        #restart raop sink
        os.system("pactl unload-module module-raop-discover")
        os.system("sleep 2")
        os.system("pactl load-module module-raop-discover")
        os.system("pactl unload-module module-raop-sink")
    else: 
        #move input
        for input_id in sink_inputs:
            os.system(f"pactl move-sink-input {input_id} {SINK_LINEOUT}")
        with open_toggle_state_file("w") as f:
            f.write("lineout")
        
@app.route('/')
def index():
    with open_toggle_state_file() as f:
        current_output = f.read().strip()
    return render_template("index.html", current_output=current_output)

@app.route('/toggle' , methods=['POST'])
def toggle():
    toggle_audio()
    return ("ok")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3001)
              



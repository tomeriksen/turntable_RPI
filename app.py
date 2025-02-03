from flask import Flask, render_template, request
from dataclasses import dataclass
import os

app = Flask(__name__)


TOGGLE_STATE_FILE = "/tmp/toggle-audio-state"
SINK_STATE_FILE = "/tmp/audio-sink-state"
SINK_LINEOUT = "alsa_output.platform-bcm2835_audio.stereo-fallback"
SINK_HOMEPOD = "raop_sink.Vardagsrum.local.10.0.1.22.7000"
global output_sinks, current_sink_id

@dataclass
class Sink:
    id: int
    name: str
    airplay: bool = False
    

def fetch_sink(sink_id):
    global output_sinks
    fallback_sink = None
    for sink in output_sinks:
        if sink.id == sink_id:
            return sink
        elif not sink.airplay:
            fallback_sink = sink
    return fallback_sink

def PrettifyOutputs(output_sinks):
    pretty_output_sinks = []
    for sink in output_sinks:
        tmp_sink = sink
        if "alsa" in tmp_sink.name:
            tmp_sink.name = "Lineout"
        elif "raop" in tmp_sink.name:
            #replase "raop" with "Airplay: "
            tmp_sink.name = tmp_sink.name.replace("raop.", "Airplay: ")
        pretty_output_sinks.append(tmp_sink)
    return pretty_output_sinks


def init():
    restart_raop_sinks()
    global output_sinks, current_sink_id
    current_sink_id = -1
    output_sinks = []
    with open_sink_state_file() as f:
        current_output_name = f.read().strip()
    

    #list all raop sinks
    sinks = os.popen("pactl list sinks short").read().split()
    for sink in sinks:
        airplay = False
        #first element is the id, 2nd item is the name
        sink_id = sink.split(".")[1]
        sink_name = sink.split(".")[2]
        if sink_name == current_output_name:
            current_sink_id = sink_id
        #if name contains raop, it's an airplay sink
        if "raop" in sink_name:
            output_sinks.append(Sink(sink_id, sink_name, airplay=True))
        elif "alsa" in sink_name:
            output_sinks.append(Sink(sink_id, sink_name, airplay=False))
        #else ignore
    
def restart_raop_sinks():
    #unload module
    os.system("pactl unload-module module-raop-discover")
    os.system("sleep 2")
    os.system("pactl load-module module-raop-discover")
       
def open_sink_state_file(write=False):
    #check if file exists
    if not os.path.exists(SINK_STATE_FILE):
        #create
        with open(SINK_STATE_FILE,"w") as f:
            f.write("None")

    if write:
        return open(SINK_STATE_FILE, "w")
    else:
        return open(SINK_STATE_FILE, "r")

def switch_audio(new_output_id):
    global output_sinks, current_sink_id
    new_output_sink = fetch_sink(new_output_id)

    if new_output_id == current_sink_id:
        return #no need to switch
    if new_output_sink == None: #raise error
        return
    
    #move input
    sink_inputs = os.popen("pactl list sink-inputs short | awk '{print $1}'").read().split()
    
    for sink in output_sinks:
        if sink.id == new_output_id:
            for input_id in sink_inputs:
                os.system(f"pactl move-sink-input {input_id} {sink.id}") #check if this works
            if sink.airplay:
                if not new_output_sink.airplay:
                    restart_raop_sinks()
            
            with open_sink_state_file("w") as f:
                f.write(sink.name)
            current_sink_id = new_output_id
            break
    

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
    pretty_output_sinks = PrettifyOutputs(output_sinks)
    return render_template("index.html", current_output=fetch_sink(current_sink_id), output_sinks=pretty_output_sinks)
@app.route('/switch' , methods=['POST'])
def switch(new_output_id):
    switch_audio(new_output_id)
    return ("ok")
@app.route('/toggle' , methods=['POST'])
def toggle():
    toggle_audio()
    return ("ok")

if __name__ == '__main__':
    init()
    app.run(host='0.0.0.0', port=3001)
              



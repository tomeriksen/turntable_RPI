from dataclasses import dataclass
import os
@dataclass
class Sink:
    id: int
    name: str
    airplay: bool = False

class SinkList:
    def __init__(self):
        sinkArray = []
        selected = -1
    def find_by_name(self, sink_name):
        for sink in self.sinkArray:
           if sink.name == sink_name:
                return sink
        return None
    def find_by_id (self, sink_id):
        for sink in self.sinkArray:
            if sink.id == sink_id:
                return sink
        return None


@dataclass
class SinkInput:
    id: int
    name: str
    sink_id: int = -1


#Global variables
SINK_STATE_FILE = "/tmp/audio-sink-state"
# If the name of the sink-input contains any of these keywords, it will be skipped
SYSTEM_AUDIO_KEYWORDS = {"loopback", "system"}

global std_out, current_sink
std_out = -1 #will this run when imported from another file?


#MAIN FUNCTION
# switch_audio() The main function that switches the audio output to the new sink
def switch_audio (new_sink_id):
    sink_outputs = get_sink_outputs() #also sets std_out
    sink_inputs = get_sink_inputs()
    current_sink_name = get_current_state()

    if current_sink_name is None:
        print("No previous sink state found")
        current_sink = sink_outputs.find_by_id(std_out)
    else:
        current_sink = sink_outputs.find_by_name(current_sink_name)
    new_sink = sink_outputs.find_by_id(new_sink_id)
    if new_sink is None:
        print(f"Sink {new_sink_id} not found")
        return
    
    if new_sink != current_sink:
        for i in sink_inputs:
            if any(keyword in i.name.lower() for keyword in SYSTEM_AUDIO_KEYWORDS):
                print(f"Skipping system audio input {i.id} ({i.name})")
                continue  # Do'nt move system audio inputs
            print(f"Moving sink-input {i.id} to {i.name}")
            os.system(f"pactl move-sink-input {input_id} {new_sink}")

    # Spara nya sinken i filen
    write_sink_state(new_sink.name)
    if new_sink.airplay:
        print("Restarting raop sinks")
        restart_raop_sinks()
    print(f"Switched audio to {new_sink.name}")

#UTILITY FUNCTIONS
def get_sink_inputs():
    """ Hämtar alla sink-inputs och returnerar en lista av tuples (input_id, media_name) """
    result = subprocess.run(["pactl", "list", "sink-inputs"], capture_output=True, text=True)
    inputs = []
    input_id = None
    media_name = None
    output_id = None
    
    for line in result.stdout.split("\n"):
        if "Sink Input #" in line:
            input_id = line.split("#")[1].strip()
            continue
        if "media.name" in line:
            media_name = line.split("=")[1].strip().strip('"')
            continue
        if "Sink:" in line:
            sink_id = line.split("= ")[1].strip()
        if input_id and media_name and sink_id:
            inputs.append(SinkInput(input_id, media_name, output_id))
            input_id = None
            media_name = None
            output_id=None #NOTE: will only list connected sinks
            

    return inputs

def get_sink_outputs():
    global std_out
    result = os.popen("pactl list sinks short").read().strip()
    sinks = SinkList()
    
    for line in result:
        if len(sink) == 0:
            break
        airplay = False
        #first element is the id, 2nd item is the name
        sink_id = sink.split("\t")[0]
        sink_name = sink.split("\t")[1]
        if "raop" in sink_name:
            sinks.sink_array.append(Sink(sink_id, sink_name, airplay=True))
        elif "alsa" in sink_name:
            sinks.sink_array.append(Sink(sink_id, sink_name, airplay=False))
            std_out = sink_id
    return sinks

def get_inputs_connected_to_sink(sink_inputs, sink):
    result = []
    for i in sink_inputs:
        if i.sink_id == sink.id:
            result.append (i)
    return result
            
def get_current_state ():
    #check if file exists
    if not os.path.exists(SINK_STATE_FILE):
        #create file
        with open(SINK_STATE_FILE,"w") as f:
            f.write("None")
    with open(SINK_STATE_FILE, "r") as f:
        sink_name = f.read().strip()
    if sink_name == "None":
        return None
    return sink_name
    
def write_sink_state (sink_name):
    with open(SINK_STATE_FILE, "w") as f:
        f.write(sink_name)

def restart_raop_sinks():
    #unload module
    os.system("pactl unload-module module-raop-discover")
    os.system("sleep 2")
    os.system("pactl load-module module-raop-discover")

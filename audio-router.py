
# switch_audio - switchar sink från CURRENT_SINKS[0] till sink
#more_audio - öppnar en ny sink och lägger till den till CURRENT_SINKS
#kill_audio - tar bort en sink från CURRENT_SINKS och stänger loopbacken
#kill_all_audio - stänger alla sinks och loopbackar
# monitor - kollar att alla sparade sinks finns i systemet. Laddar om module-raop-discover
# signal funktion som lyssnar efter signaler från andra program. 


#SUPPORTFUNKTIONER
#KLASSER
# Loopback - klass som hanterar loopbackar. Brygga mellan pulseaudio och pipewire
# Nodes - klass som hanterar sources / sinks 
# Sinklist - klass som hanterar en lista av sinks.
# Sink - klass som hanterar sinks. Ärver från Node.
# Source - klass som hanterar sources. Ärver från Node.
# Node - klass som hanterar en nod.
# AudioRouter - huvudklass som hanterar ljudväxlingar.

import os
import json
import subprocess
import time
import copy
import signal
import threading
from dataclasses import dataclass

LOG_FILE = "/tmp/audio-router.log"

def log_message(message):
    with open(LOG_FILE, "a") as f:
        f.write(f"{message}\n")
    print(message)  # Also print to system logs for debugging

log_message ("Start audio-router" + str (time.time()))

class Loopback:
    def __init__(self, source, sink):
        result = subprocess.run(
            ["pactl", "load-module", "module-loopback", f"source={source.id}", f"sink={sink.id}"],
            capture_output=True, text=True, check=False)

        result = result.stdout.split()
        self.id = result[0]
        self.source = source
        self.sink = sink
    
    def get_pipewire_ids(self):
        try:
            # Kör pw-dump och ladda JSON-utdata
            result = subprocess.run(["pw-dump"], capture_output=True, text=True, check=True)
            nodes = json.loads(result.stdout)

            # Filtrera noder som har rätt PulseAudio-modul-ID
            node_ids = []
            for node in nodes:
                if "info" in node and "props" in node["info"]:
                    props = node["info"]["props"]
                    module_id = props.get("pulse.module.id")

                    # Only print nodes that contain module ID
                    if module_id is not None:
                        print(f"Node ID: {node['id']}, Module ID: {module_id}")
                        node_ids.append(node['id'])

                if "info" in node and "props" in node["info"]:
                    
                    module_id = node["info"]["props"].get("pulse.module.id")
                   
                   
        

            return node_ids
        
        except subprocess.CalledProcessError as e:
            print(f"Fel vid körning av pw-dump: {e}")
            return []
        except json.JSONDecodeError as e:
            print(f"Fel vid tolkning av JSON: {e}")
            return []

    def remove(self):
        # delete the pw loopback modules
        node_ids = self.get_pipewire_ids()
        for node_id in node_ids:
            subprocess.run(["pw-cli", "destroy", str(node_id)], check=True)
        
    def __enter__(self):
        #return self to be used within the with block
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Clean up resources when exiting the with block
        self.remove()

    # Optionally, you can define __del__ as a backup.
    def __del__(self):
        try:
            self.remove()
        except Exception:
            pass  # Avoid errors during interpreter shutdown
@dataclass
class Node:
    id: int
    name: str

@dataclass
class Sink(Node): 
    airplay: bool = True

class Nodes:
    def __init__(self):
        self.node_array = []

    def get_node_by_id(self, node_id):
        for node in self.node_array:
            if node.id == node_id:
                return node
        return None
    
    def get_node_by_name(self, node_name):
        for node in self.node_array:
            if node.name == node_name:
                return node
        return None
    
    def append(self, node):
        self.node_array.append(node)
    
    def remove(self, node_id):
        for node in self.node_array:
            if node.id == node_id:
                self.node_array.remove(node)
                return
        print(f"Node {node_id} not found")

    def __iter__(self):
        return iter(self.node_array)
    
    def __len__(self):
        return len(self.node_array)
    def __getitem__(self,i):
        return self.node_array[i]



#########################################
###########AudioRouter Class ############
#########################################
    
class AudioRouter:

    def __init__(self):
        self.all_sinks = self.get_raop_sinks()
        self.all_sources = self.get_all_sources()
        
        try:
            self.current_source = self.all_sources.get_node_by_name("alsa_input.platform-soc_sound.stereo-fallback")
        except AttributeError:
            self.current_source = None
            print("No input source found")
        self.loopbacks = []
        #remove all loopbacks currently running in the system
        

        # Koppla signaler
        signal.signal(signal.SIGUSR1, self.handle_signal) # Hoppa till nästa sink
        signal.signal(signal.SIGUSR2, self.handle_signal) # Stäng av alla loopbackar
        signal.signal(signal.SIGHUP, self.handle_signal) # starta om raop discover
        signal.signal(signal.SIGTERM, self.handle_signal) # Stäng av alla loopbackar
        signal.signal(signal.SIGINT, self.handle_signal)


    def get_raop_sinks(self):
        try:
            result = subprocess.run(["pactl", "list", "sinks", "short"], capture_output=True, text=True, check=True)

            sinks = Nodes()
            for line in result.stdout.split("\n"):  # Split into lines
                if "raop" in line:  # Filter for RAOP sinks
                    parts = line.split()  # Split by whitespace
                    if len(parts) > 1:  # Ensure we have enough data
                        id = parts[0]  # First column (sink ID)
                        name = parts[1]  # Second column (sink name)
                        sinks.append(Sink(int(id), name, airplay=True))  # Create Sink object
                        #log_message ("Adding sink: " + name)
            return sinks
        except subprocess.CalledProcessError as e:
            print(f"Error running pactl: {e}")
            return []
    
    def get_next_sink_id(self):
        """Returns the ID of the next available RAOP sink, cycling through them."""
        #refresh sinks
        self.all_sinks = self.get_raop_sinks()
        
        if not self.all_sinks:  # If no sinks exist, return None
            return None

        # If no loopback exists, return the first sink
        if not self.loopbacks:
            return self.all_sinks[0].id
        
        #id might have changed, fetch name of sink in loopback
        last_sink_name = self.loopbacks[-1].sink.name

        # Get all sink IDs and names as a list
        sink_ids , sink_names = zip(*[(sink.id, sink.name) for sink in self.all_sinks])
        

        # Find index of the last used sink (default to -1 if not found)
        try:
            last_index = sink_names.index(last_sink_name)
        except ValueError:
            last_index = -1  # If sink is missing, start from the first one
     

        # Get the next sink in a circular manner
        next_index = (last_index + 1) % len(sink_ids)
        return sink_ids[next_index]


    
    def get_all_sources(self):
        result = subprocess.run(["pactl", "list", "sources", "short"], capture_output=True, text=True, check=True)
        result = result.stdout.strip()
        sources = Nodes()
        for line in result.split("\n"):
            id = line.split()[0]
            name = line.split()[1]
            if "raop" in name: #skip raop sources
                continue
            sources.append(Node(int(id), name))
        return sources
    
        
    
    def switch_audio(self, sink_id):
        new_sink = self.all_sinks.get_node_by_id(sink_id)
        if not new_sink:
            print(f"Sink {sink_id} not found")
            return
        self.kill_all_audio()
        #create new loopback
        loopback = Loopback(self.current_source, new_sink)
        self.loopbacks.append(loopback)

    def more_audio(self, sink_id):
        new_sink = self.all_sinks.get_node_by_id(sink_id)
        if not new_sink:
            print(f"Sink {sink_id} not found")
            return
        loopback = Loopback(self.current_source, new_sink)
        self.loopbacks.append(loopback)
    
    def kill_audio(self, sink_id):
        for loopback in self.loopbacks:
            if loopback.sink == sink_id:
                loopback.remove()
                self.loopbacks.remove(loopback)
                return
        print(f"Loopback for sink {sink_id} not found")
    
    def kill_all_audio(self):
        for loopback in self.loopbacks:
            loopback.remove()
        self.loopbacks = []
    
    def handle_signal(self, sig, frame):
        """Hanterar inkommande signaler och utför åtgärder"""
        
        """if sig == signal.SIGUSR1:
            print("Mottog SIGUSR1 - Växlar ljudutgång")
            self.switch_audio(self.get_next_sink_id())"""
        if sig == signal.SIGUSR1:
            log_message("Handling SIGUSR1: Switching RAOP sink")

            # Debugging: Log all available sinks before switching
            all_sinks = router.get_raop_sinks()
            log_message(f"Available sinks: {[sink.id for sink in all_sinks]}")

            next_sink_id = router.get_next_sink_id()
            log_message(f"Next sink ID to switch to: {next_sink_id}")

            if next_sink_id is None:
                log_message("ERROR: No valid sink found! Check pactl output.")
                return

            router.switch_audio(next_sink_id)
            log_message(f"Switched audio to sink {next_sink_id}")
        elif sig == signal.SIGUSR2:
            print("Mottog SIGUSR2 - Stänger av alla loopback")
            if self.loopbacks:
                self.kill_all_audio()
        elif sig == signal.SIGTERM or sig == signal.SIGINT:
            print("Mottog SIGTERM/SIGINT - Stänger ner allt ljud")
            self.kill_all_audio()
            exit(0)


    
    def monitor(self):
        def parse_pactl_module_output(output):
            #Parses pactl module output into a structured list of dictionaries.
            modules = []
            current_module = {}

            for line in output.split("\n"):
                line = line.strip()
                if not line:
                    continue  # Skip empty lines

                if line.startswith("Module #"):
                    if current_module:  # Save the previous module
                        modules.append(current_module)
                    current_module = {"Properties": {}}
                    current_module["ID"] = line.split("#")[1].strip()
                elif line.startswith("Name:"):
                    current_module["Name"] = line.split(":", 1)[1].strip()
                elif line.startswith("Argument:"):
                    current_module["Arguments"] = line.split(":", 1)[1].strip()
                elif line.startswith("Usage counter:"):
                    current_module["Usage Counter"] = line.split(":", 1)[1].strip()
                elif "=" in line:
                    key, value = line.split("=", 1)
                    current_module["Properties"][key.strip()] = value.strip().strip('"')

            if current_module:
                modules.append(current_module)  # Add last module

            return modules
        
        while True:
            time.sleep(10)
            #Check if all sinks are still available
            print ("hello")
            new_sinks = self.get_raop_sinks()
            for sink in self.all_sinks:
                if not new_sinks.get_node_by_id(sink.id):
                    #sink does not exist anymore
                    print(f"VARNING: Sink {sink.name} (ID {sink.id}) försvunnen! Laddar om RAOP.")

                    old_loopbacks = copy.deepcopy(self.loopbacks)
                    self.kill_all_audio()
                    reload_module_raop_discover()
                    self.all_sinks = self.get_raop_sinks() #sinks may have changed after reload
                    #try to reestablish loopbacks
                    for old_loopback in old_loopbacks:
                        new_sink = self.all_sinks.get_node_by_name(old_loopback.sink.name)
                        if new_sink:
                            loopback = Loopback(old_loopback.source, new_sink)
                            self.loopbacks.append(loopback)
                    break
            """
            #check if sinks are RUNNING
            result = subprocess.run(["pactl", "list", "modules"], capture_output=True, text=True, check=True)
            result = result.stdout
            if not result:
                time.sleep(10)
                continue
            modules = parse_pactl_module_output(result)
            result_sinks = subprocess.run(["pactl", "list", "sinks", "short"], capture_output=True, text=True, check=True)
            result_sinks.stdout.strip()
            for loopback in self.loopbacks:
                for module in modules:
                    if "Arguments" in module:
                        if "sink="+loopback.sink.id in module["Arguments"]:
                            #check if module is running
                            try:
                                found_loopback = False
                                for line in result_sinks.stdout.split("\n"):
                                    if loopback.sink in line:
                                        found_loopback = True
                                        if "RUNNING" not in line:
                                            print(f"Sink {loopback.sink} not running")
                                            raise Exception
                                        else:
                                            break
                                if not found_loopback:
                                    print(f"Loopback for sink {loopback.sink} not found")
                                    raise Exception
                                   
                            except:
                                self.kill_audio(loopback.sink)
                                print(f"Loopback for sink {loopback.sink} not running")
                                break
                                print(f"Killing audio to sink {loopback.sink}")

            """



            
    def run(self):
        self.monitor()
         


RELOAD_LOCK = threading.Lock()  # Create a lock object

def reload_module_raop_discover():
    """Safely reloads module-raop-discover"""
    with RELOAD_LOCK:  # Correct way to use a lock
        print("Restarting module-raop-discover...")
        os.system("pactl unload-module module-raop-discover")
        time.sleep(2)  # Avoid race conditions
        os.system("pactl load-module module-raop-discover")
        print("RAOP discover restarted.")

# Wait for pactl to be ready
def wait_for_pactl():
    retries = 10
    for i in range(retries):
        try:
            subprocess.run(["pactl", "list", "sources", "short"], check=True, capture_output=True, text=True)
            print("pactl is ready")
            return
        except subprocess.CalledProcessError:
            print(f"pactl not ready, retrying... ({i+1}/{retries})")
            time.sleep(2)
    print("pactl failed to start after retries. Exiting.")
    exit(1)


if __name__ == "__main__":
    wait_for_pactl()
    router = AudioRouter()
    print("PID:", os.getpid())
    router.run()
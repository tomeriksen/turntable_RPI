
# switch_audio - switchar sink frÃ¥n CURRENT_SINKS[0] till sink
#more_audio - Ã¶ppnar en ny sink och lÃ¤gger till den till CURRENT_SINKS
#kill_audio - tar bort en sink frÃ¥n CURRENT_SINKS och stÃ¤nger loopbacken
#kill_all_audio - stÃ¤nger alla sinks och loopbackar
# monitor - kollar att alla sparade sinks finns i systemet. Laddar om module-raop-discover
# signal funktion som lyssnar efter signaler frÃ¥n andra program. 


#SUPPORTFUNKTIONER
#KLASSER 
# Loopback - klass som hanterar loopbackar. Brygga mellan pulseaudio och pipewire
# Nodes - klass som hanterar sources / sinks 
# Sinklist - klass som hanterar en lista av sinks.
# Sink - klass som hanterar sinks. Ãrver frÃ¥n Node.
# Source - klass som hanterar sources. Ãrver frÃ¥n Node.
# Node - klass som hanterar en nod.
# AudioRouter - huvudklass som hanterar ljudvÃ¤xlingar.

import os
import json
import subprocess
import time
import copy
import signal
import threading
from dataclasses import dataclass
from flash_led import FlashLedManager
from send_push import send_push
from dotenv import load_dotenv




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
            # KÃ¶r pw-dump och ladda JSON-utdata
            result = subprocess.run(["pw-dump"], capture_output=True, text=True, check=True)
            nodes = json.loads(result.stdout)

            # Filtrera noder som har rÃ¤tt PulseAudio-modul-ID
            node_ids = []
            for node in nodes:
                if "info" in node and "props" in node["info"]:
                    props = node["info"]["props"]
                    module_id = props.get("pulse.module.id")

                    # Only print nodes that contain module ID
                    if module_id is not None:
                        if int(module_id) == int(self.id):
                            print(f"Node ID: {node['id']}, Module ID: {module_id}")
                            node_ids.append(node['id'])

                if "info" in node and "props" in node["info"]:
                    
                    module_id = node["info"]["props"].get("pulse.module.id")
                   
                   
        

            return node_ids
        
        
        except subprocess.CalledProcessError as e:
            print(f"Fel vid kÃ¶rning av pw-dump: {e}")
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
    
    def get_index_by_name(self, node_name):
        for i in range(len(self.node_array)):
            if self.node_array[i].name == node_name:
                return i
        return -1
    
    def is_node_name (self, pattern):
        for node in self.node_array:
            if pattern.lower() in node.name.lower():
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
        self.led_manager = FlashLedManager()
        self.led_manager.flash_ok()
        
        restart_audio_server = not raop_module_loaded()
        if restart_audio_server:
            restart_pulseaudio()
        
        self.all_sinks = self.get_raop_sinks(restart_audio_server)
        self.all_sources = self.get_all_sources(restart_audio_server)
        
        try:
            self.current_source = self.all_sources.get_node_by_name("alsa_input.platform-soc_sound.stereo-fallback")
            if not self.current_source:
                raise Exception
        except:
            self.current_source = None
            print("FATAL: No input source found")
        self.loopbacks = []
        #remove all loopbacks currently running in the system
        
                
        

        # Koppla signaler
        signal.signal(signal.SIGUSR1, self.handle_signal) # Hoppa till nÃ¤sta sink
        signal.signal(signal.SIGUSR2, self.handle_signal) # StÃ¤ng av alla loopbackar
        signal.signal(signal.SIGHUP, self.handle_signal) # starta om raop discover
        signal.signal(signal.SIGTERM, self.handle_signal) # StÃ¤ng av alla loopbackar
        signal.signal(signal.SIGINT, self.handle_signal)

    def __exit__(self):
        self.kill_all_audio()
        self.led_manager.remove_all_leds()


    def get_raop_sinks(self, wait_after_restart = False):
        timeout = 1
        sinks = Nodes()
        if wait_after_restart:
            timeout = 10
        for i in range(timeout):
            try:
                result = subprocess.run(["pactl", "list", "sinks", "short"], capture_output=True, text=True, check=True)

                for line in result.stdout.split("\n"):  # Split into lines
                    if "raop" in line:  # Filter for RAOP sinks
                        parts = line.split()  # Split by whitespace
                        if len(parts) > 1:  # Ensure we have enough data
                            id = parts[0]  # First column (sink ID)
                            name = parts[1]  # Second column (sink name)
                            sinks.append(Sink(int(id), name, airplay=True))  # Create Sink object
                            #log_message ("Adding sink: " + name)
                if len(sinks):
                    break
                else:
                    log_message(f"Waiting for sinks... ({i+1}/{timeout})")
            except subprocess.CalledProcessError as e:
                print(f"Error running pactl: {e}")
                self.led_manager.flash_error()
                return []
            time.sleep(1)
        self.led_manager.flash_ok()
        return sinks
    
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
    
    def get_next_sink_name(self):
        """Returns the ID of the next available RAOP sink, cycling through them."""
        #refresh sinks
        self.all_sinks = self.get_raop_sinks()
        
        if not self.all_sinks:  # If no sinks exist, return None
            return None

        # If no loopback exists, return the first sink
        if not self.loopbacks:
            return self.all_sinks[0].name
        
        #id might have changed, fetch name of sink in loopback
        last_sink_name = self.loopbacks[-1].sink.name

        # Find index of the last used sink (default to -1 if not found)
        last_index =  self.all_sinks.get_index_by_name(last_sink_name)

        # Get the next sink in a circular manner
        next_index = (last_index + 1) % len(self.all_sinks)
        return self.all_sinks[next_index].name
    
    def get_prev_sink_name(self):
        """Returns the ID of the next available RAOP sink, cycling through them."""
        #refresh sinks
        self.all_sinks = self.get_raop_sinks()
        
        if not self.all_sinks:  # If no sinks exist, return None
            return None

        # If no loopback exists, return the first sink
        if not self.loopbacks:
            return self.all_sinks[0].name
        
        #id might have changed, fetch name of sink in loopback
        last_sink_name = self.loopbacks[-1].sink.name

        # Find index of the last used sink (default to -1 if not found)
        last_index =  self.all_sinks.get_index_by_name(last_sink_name)

        # Get the next sink in a circular manner
        next_index = (last_index - 1) % len(self.all_sinks)
        return self.all_sinks[next_index].name

   
    def get_all_sources(self, wait_after_restart = False):
        timeout = 1
        if wait_after_restart:
            timeout = 10
        for i in range(timeout):
            
            result = subprocess.run(["pactl", "list", "sources", "short"], capture_output=True, text=True, check=True)
            result = result.stdout.strip()
            sources = Nodes()
            for line in result.split("\n"):
                id = line.split()[0]
                name = line.split()[1]
                if "raop" in name: #skip raop sources
                    continue
                sources.append(Node(int(id), name))
            if len(sources):
                return sources
            else:
                log_message(f"Waiting for sources... ({i+1}/{timeout})")
                time.sleep(1)
        log_message("ERROR: No valid sources found after waiting. Check PipeWire/PulseAudio!", True, "get_all_sources")
    
    def sink_in_loopbacks(self, sink_name):
        for loopback in self.loopbacks:
            if loopback.sink.name == sink_name:
                return True
        return False
        
    
    def switch_audio(self, sink_name):
        new_sink = self.all_sinks.get_node_by_name(sink_name)
        if not new_sink:
            print(f"Sink {sink_name} not found")
            return
        self.kill_all_audio()
        #create new loopback
        loopback = Loopback(self.current_source, new_sink)
        self.loopbacks.append(loopback)

    def more_audio(self, sink_name):
        new_sink = self.all_sinks.get_node_by_name(sink_name)
        if not new_sink:
            log_message(f"Sink {sink_name} not found", True, "more_audio")
            self.led_manager.flash_error()
            return
        if self.sink_in_loopbacks(sink_name):
            log_message (f"Tried to open already active sink {sink_name}")
        else:
            loopback = Loopback(self.current_source, new_sink)
            self.loopbacks.append(loopback)
            log_message (f"Opened sink between {self.current_source} and {sink_name}")
            self.led_manager.flash_ok()
    
    def kill_audio(self, sink_name):
        for loopback in self.loopbacks:
            if loopback.sink.name == sink_name:
                loopback.remove()
                self.loopbacks.remove(loopback)
                log_message (f"Remove sink {sink_name} from loopback")
                return
        log_message(f"Loopback for sink {sink_name} not found", True, "KillAudio")
    
    def kill_all_audio(self):
        for loopback in self.loopbacks:
            loopback.remove()
        self.loopbacks = []
    
  
    def handle_signal(self, sig, frame):
        #Hanterar inkommande signaler fÃ¶r att styra ljudvÃ¤xlingen
        
        # LÃ¤s kommando frÃ¥n filen
        command = read_command()

        log_message(f"Received signal: {sig} with command: {command}")

        if sig == signal.SIGUSR1:
            if command == "mute":
                log_message("Muting audio")
                subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
                write_status("SUCCESS: muted")
            
            elif command == "next":
                next_sink_name = self.get_next_sink_name()
                if next_sink_name:
                    self.switch_audio(next_sink_name)
                    write_status(f"SUCCESS: Switched to {next_sink_name}")
                else:
                    write_status("ERROR: No valid sink found!")
            
            elif command == "prev":
                prev_sink_name = self.get_prev_sink_name()
                if prev_sink_name:
                    self.switch_audio(prev_sink_name)
                    write_status(f"SUCCESS: Switched to {prev_sink_name}")
                else:
                    write_status("ERROR: No valid sink found!")
            
            else:
                #is it part of a sink name?
                sink = self.all_sinks.is_node_name(command)
                if sink:
                    if self.sink_in_loopbacks(sink.name):
                        self.kill_audio(sink.name)
                        write_status(f"SUCCESS: Shut off {sink.name}")

                    else:
                        self.more_audio(sink.name)
                        write_status(f"SUCCESS: Switched to {sink.name}")
                    self.led_manager.flash_ok()
                else: 
                    write_status(f"ERROR: Unknown command '{command}'")
                    self.led_manager.flash_error()
        
        elif sig == signal.SIGUSR2:
            log_message("Reloading PulseAudio")
            restart_pulseaudio()
            write_status("PulseAudio restarted")
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
            print ("monotor 10 s loop")
            new_sinks = self.get_raop_sinks()
            for sink in self.all_sinks:
                if not new_sinks.get_node_by_id(sink.id):
                    #sink does not exist anymore
                    log_message(f"WARNING: Sink {sink.name} (ID {sink.id}) dissapeared! Reloading RAOP.", push=True, title="AudioRouter.monitor")

                    old_loopbacks = copy.deepcopy(self.loopbacks)
                    self.kill_all_audio()
                    restart_pulseaudio()
                    #reload_module_raop_discover()
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
RESTART_LOCK = threading.Lock()  # Create a lock object

def reload_module_raop_discover(unload_first= True):
    """Safely reloads module-raop-discover"""
    with RELOAD_LOCK:  # Correct way to use a lock
        print("Restarting module-raop-discover...")
        if unload_first:
            os.system("pactl unload-module module-raop-discover")
            time.sleep(2)  # Avoid race conditions
        os.system("pactl load-module module-raop-discover")
        print("RAOP discover restarted.")

def raop_module_loaded ():
    raop_loaded = False
    result = subprocess.run(["pactl", "list", "modules", "short"],capture_output=True, text=True, check=True)
    for line in result.stdout.split("\n"):  # Split into lines
        if "module-raop-discover" in line:
            raop_loaded = True
            log_message ("Raop module is loaded")
            break
    #load raop module
    if not raop_loaded:
        log_message ("Raop module is not loaded", True, "raop_module_loaded")
    return raop_loaded

def restart_pulseaudio ():
    try:
        with RELOAD_LOCK:
            log_message("Restarting Pulse Audio and Pipewire")
            subprocess.run (["systemctl" ,"--user", "restart",  "pipewire", "pipewire-pulse"])
    except subprocess.CalledProcessError:
        log_message ("Failed to restart Pipewire and PulseAudio")
    if not raop_module_loaded():
        reload_module_raop_discover(unload_first=False)
        
    
    
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


LOG_FILE = "/tmp/audio-router.log"

def log_message(message, push=False, push_title = "Turntable"):
    with open(LOG_FILE, "a") as f:
        f.write(f"{message}\n")
    print(message)  # Also print to system logs for debugging
    if push or "ERROR" in message.upper():
        send_push (push_title, message)


STATUS_FILE = "/tmp/audio-router-status.log"
def write_status(message):
    """Skriver status om senaste åtgärden"""
    with open(STATUS_FILE, "w") as f:
        f.write(message + "\n")
    log_message(f"STATUS: {message}")
    
COMMAND_FILE = "/tmp/audio-router-command"
def read_command():
    try:
        with open(COMMAND_FILE, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        log_message ("No command sent")
        return None



if __name__ == "__main__":
    load_dotenv()

    PUSHOVER_USER = os.getenv("PUSHOVER_USER")
    PUSHOVER_TOKEN = os.getenv("PUSHOVER_TOKEN")
    
    wait_for_pactl()
    log_message ("Start audio-router" + str (time.asctime()))
    router = AudioRouter()
    log_message("PID:", os.getpid())
    router.run()



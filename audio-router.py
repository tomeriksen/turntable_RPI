
# switch_audio - switchar sink frÃ¥n CURRENT_SINKS[0] till sink
#more_audio - Ã¶ppnar en ny sink och lÃ¤gger till den till CURRENT_SINKS
#kill_audio - tar bort en sink frÃ¥n CURRENT_SINKS och stÃ¤nger loopbacken
#kill_all_audio - stÃ¤nger alla sinks och loopbackar
# monitor - kollar att alla sparade sinks finns i systemet. Laddar om module-raop-discover
# signal funktion som lyssnar efter signaler frÃ¥n andra program. 



import os
import subprocess
import time
import copy
import signal
import threading
from systemd import journal
from flash_led import FlashLedManager
from send_push import send_push
from dotenv import load_dotenv
from nodes import Loopback, Node, Nodes, Sink
from dataclasses import dataclass, field

@dataclass
class EventCommand:
    action: str
    sink: str = ""
    timestamp: str = field(default_factory=lambda: time.asctime())



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
            log_message("FATAL: No input source found")
        self.loopbacks = []
        

        

        #remove all loopbacks currently running in the system
        
                
        

        # Koppla signaler
        signal.signal(signal.SIGUSR1, self.handle_signal) # Hoppa till nÃ¤sta sink
        signal.signal(signal.SIGUSR2, self.handle_signal) # StÃ¤ng av alla loopbackar
        signal.signal(signal.SIGHUP, self.handle_signal) # starta om raop discover
        signal.signal(signal.SIGTERM, self.handle_signal) # StÃ¤ng av alla loopbackar
        signal.signal(signal.SIGINT, self.handle_signal)

        #signal management
        self.command_queue = []
        self.signal_event = threading.Event()

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
                log_message(f"Error running pactl: {e}")
                self.led_manager.flash_error()
                return []
            time.sleep(1)
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
            log_message(f"When switching audio sink, Sink {sink_name} not found")
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
            log_message (f"Opened sink between {self.current_source} and {new_sink}")
            self.led_manager.flash_ok()
    
    def kill_audio(self, sink_name):
        for loopback in self.loopbacks:
            if loopback.sink.name == sink_name:
                try:
                    loopback.remove()
                    self.loopbacks.remove(loopback)
                    log_message (f"Remove sink {sink_name} from loopback")
                    return
                except:
                    log_message(f"Loopback for sink {sink_name} not found", True, "KillAudio")
    
    def kill_all_audio(self):
        for loopback in self.loopbacks:
            loopback.remove()
        self.loopbacks = []
    
  
    def handle_signal(self, sig, frame):
        #Hanterar inkommande signaler för att styra ljudväxlingen
        
        # Läs kommando från filen
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
                    self.command_queue.append(EventCommand(action="switch", sink=next_sink_name))
                    #self.switch_audio(next_sink_name)
                    #write_status(f"SUCCESS: Switched to {next_sink_name}")
                else:
                    write_status("ERROR: No valid sink found!")
            
            elif command == "prev":
                prev_sink_name = self.get_prev_sink_name()
                if prev_sink_name:
                    self.command_queue.append(EventCommand(action="switch", sink=prev_sink_name))

                    #self.switch_audio(prev_sink_name)
                    #write_status(f"SUCCESS: Switched to {prev_sink_name}")
                else:
                    write_status("ERROR: No valid sink found!")
            
            elif command: #if command is not empty
                #is it part of a sink name?
                sink = self.all_sinks.is_node_name(command)
                if sink:
                    #check if sink is already in loopbacks, then kill it
                    if self.sink_in_loopbacks(sink.name):
                        self.command_queue.append(EventCommand(action="kill", sink=sink.name))
                        #self.kill_audio(sink.name)
                        #write_status(f"SUCCESS: Shut off {sink.name}")
                    #if not, open a loopback
                    else:
                        self.command_queue.append(EventCommand(action="add", sink=sink.name))
                        """#self.more_audio(sink.name)
                        write_status(f"SUCCESS: Added {sink.name} as sound output.")
                        #loop for debugging purposes. remove later
                        for loopback in self.loopbacks:
                            if loopback.sink.name == sink.name:
                                print (f"pw ids: {loopback.get_pipewire_ids()}")
                                break"""
                else: 
                    write_status(f"ERROR: Unknown command '{command}'")
                    self.led_manager.flash_error()
            self.signal_event.set() #wake up monitor thread
        
        elif sig == signal.SIGUSR2:
            #log_message("Reloading PulseAudio")
            self.command_queue.append(EventCommand(action="kill_all"))
            self.command_queue.append(EventCommand(action="restart"))
            #restart_pulseaudio()
            #write_status("PulseAudio restarted")
            self.signal_event.set() #wake up monitor thread

        elif sig == signal.SIGTERM or sig == signal.SIGINT:
            log_message("Received SIGTERM/SIGINT - Shutting down all audio loopbacks", push = True, push_title="AudioRouter.handle_signal")
            self.kill_all_audio()
            
            exit(0)


    
    def monitor(self):
        def parse_pactl_module_output(output):
            #Parses pactl module output into a structured list of dictionaries.
            modules = []
            current_module = {}
            is_argument = False
            
            for line in output.split("\n"):
                line = line.strip()
                
                if not line:
                    continue  # Skip empty lines

                if line.startswith("Module #"):
                    if current_module:  # Save the previous module
                        modules.append(current_module)
                    current_module = {"Properties": {}, "Arguments":{}}
                    current_module["ID"] = line.split("#")[1].strip()
                    is_argument=False
                elif line.startswith("Name:"):
                    current_module["Name"] = line.split(":", 1)[1].strip()
                elif line.startswith("Argument:"):
                    if "{" not in line:
                        current_module["Arguments"] = line.split(":", 1)[1].strip()
                    else:
                        is_argument=True

                elif "}" in line: #end of argumente clause
                    is_argument=False
                elif line.startswith("Usage counter:"):
                    current_module["Usage Counter"] = line.split(":", 1)[1].strip()
                elif "=" in line:
                    key, value = line.split("=", 1)
                    if is_argument:
                        current_module["Arguments"][key.strip()] = value.strip().strip('"')
                    else:
                        current_module["Properties"][key.strip()] = value.strip().strip('"')
 

            if current_module:
                modules.append(current_module)  # Add last module

            return modules
        
        while True:
            self.signal_event.wait(timeout=10)

            while self.command_queue:
                event = self.command_queue.pop(0)
                if event.action == "switch":
                    self.switch_audio(event.sink)
                    write_status(f"SUCCESS: Switched to {event.sink}")

                elif event.action == "add":
                    self.more_audio(event.sink)
                    write_status(f"SUCCESS: Added {event.sink} as sound output.")
                    #loop for debugging purposes. remove later
                    for l in self.loopbacks:
                        if l.sink.name == event.sink:
                            print (f"pw ids: {l.get_pipewire_ids()}")
                            break
                elif event.action == "kill":
                    self.kill_audio(event.sink)
                    write_status(f"SUCCESS: Shut off {event.sink}")
                elif event.action == "kill_all":
                    self.kill_all_audio()
                    write_status("SUCCESS: All audio loopbacks shut off")
                elif event.action == "restart": 
                    restart_pulseaudio()
                    write_status("SUCCESS: PulseAudio restarted")
                else:
                    log_message(f"ERROR: Unknown event action {event.action}")
            self.signal_event.clear() #the event has been handled

            #Check if all sinks are still available
            print ("AudioRouter.monitor 10 s loop")
            new_sinks = self.get_raop_sinks()
            for sink in self.all_sinks:
                if not new_sinks.get_node_by_id(sink.id):
                    #sink does not exist anymore
                    log_message(f"WARNING: Sink {sink.name} (ID {sink.id}) dissapeared! Reloading RAOP.", push=True, push_title="AudioRouter.monitor")

                    old_loopbacks = copy.deepcopy(self.loopbacks)
                    self.kill_all_audio()
                    restart_pulseaudio()
                    #reload_module_raop_discover()
                    self.all_sinks = self.get_raop_sinks() #sinks may have changed after reload
                    #try to reestablish loopbacks
                    for old_loopback in old_loopbacks:
                        new_sink = self.all_sinks.get_node_by_name(old_loopback.sink.name)
                        if new_sink:
                            new_loopback = Loopback(old_loopback.source, new_sink)
                            self.loopbacks.append(new_loopback)
                    break
            
            #check if sinks are RUNNING
            result = subprocess.run(["pactl", "list", "modules"], capture_output=True, text=True, check=True)
            result = result.stdout
           
            modules = parse_pactl_module_output(result)
            result_sinks = subprocess.run(["pactl", "list", "sinks", "short"], capture_output=True, text=True, check=True)
            result_sinks.stdout.strip()
            for loopback in self.loopbacks:
                
                for module in modules:
                    if "Arguments" in module:
                        if "sink="+str(loopback.sink.id) in module["Arguments"]:
                            #check if module is running
                            try:
                                found_loopback = False
                                for line in result_sinks.stdout.split("\n"):
                                    if str(loopback.sink.id) in line:
                                        found_loopback = True
                                        if "RUNNING" not in line:
                                            log_message(f"ERROR: Loopback for sink {loopback.sink} not running")
                                            raise Exception
                                        else:
                                            break
                                if not found_loopback:
                                    log_message(f"ERROR: Loopback for sink {loopback.sink} not found")
                                    raise Exception
                                   
                            except:
                                self.kill_audio(loopback.sink)
                                log_message(f"Killing audio to sink {loopback.sink}, and deleting Loopback sink")
                                break
                               

            



            
    def run(self):
        self.monitor()
 

###############################################
######### SUPPORT FUNCTIONS ###################
###############################################

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
        log_message ("ERROR: Failed to restart Pipewire and PulseAudio")
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
    log_message("ERROR: pactl failed to start after retries. Exiting.")
    exit(1)

##################################################
############ LOGGING & STATUS FUNCTIONS ##########
##################################################
    

LOG_FILE = "/tmp/audio-router.log"

def log_message(message, push=False, push_title = "Turntable"):
    with open(LOG_FILE, "a") as f:
        f.write(f"{message}\n")
    print(message)  # Also print to system logs for debugging
    journal.send(MESSAGE = message, SYSLOG_IDENTIFIER="audio-router") # Write to journald 
    if push or "ERROR" in message.upper():
        send_push (push_title, message)



STATUS_FILE = "/tmp/audio-router-status.log"
def write_status(message):
    """Skriver status om senaste åtgärden"""
    with open(STATUS_FILE, "w") as f:
        f.write(message + "\n")
    log_message(f"STATUS: {message}", push=True)
    
COMMAND_FILE = "/tmp/audio-router-command"
# read_command opens the COMMAND_FILE to look for parameters
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
    log_message ("Start audio-router " + str (time.asctime()), push=True)
    router = AudioRouter()
    log_message("PID: " + str(os.getpid()))
    router.run()




# switch_audio - switchar sink frÃ¥n CURRENT_SINKS[0] till sink
#more_audio - Ã¶ppnar en ny sink och lÃ¤gger till den till CURRENT_SINKS
#kill_audio - tar bort en sink frÃ¥n CURRENT_SINKS och stÃ¤nger loopbacken
#kill_all_audio - stÃ¤nger alla sinks och loopbackar
# monitor - kollar att alla sparade sinks finns i systemet. Laddar om module-raop-discover
# signal funktion som lyssnar efter signaler frÃ¥n andra program. 



import os
import subprocess
import sys
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
    sink_name: str = ""
    timestamp: str = field(default_factory=lambda: time.asctime())

global STANDARD_SOURCE, DEBUG
STANDARD_SOURCE = "alsa_input.platform-soc_sound.stereo-fallback"
DEBUG = sys.stdout.isatty()

#########################################
###########AudioRouter Class ############
#########################################
    
class AudioRouter:

    def __init__(self):
        self.led_manager = FlashLedManager()
        self.led_manager.flash_ok()

        #check if pulesaudio is running
        if not wait_for_pulseaudio():
            restart_pulseaudio(delete_os_loopbacks=True)
        
        
        #check if raop module is loaded
        if not raop_module_loaded():
            log_message("Raop module is not loaded. Reloading…", True, "AudioRouter.__init__")
            reload_module_raop_discover(unload_first=False)
        
        
        wait_for_sinks = self.get_raop_sinks(wait_after_restart=True)
        self.all_sources = self.get_all_sources()
        
        
        
        try:
            self.current_source = self.all_sources.get_node_by_name(STANDARD_SOURCE)
            if not self.current_source:
                raise Exception
        except:
            self.current_source = None
            log_message("FATAL: No input source found")
       
        

        #add any loopbacks currently running in the system
        self.loopbacks = []
        self.loopbacks = self.load_os_loopbacks()
        

        # Koppla signaler
        signal.signal(signal.SIGUSR1, self.handle_signal) # Hoppa till nÃ¤sta sink
        signal.signal(signal.SIGUSR2, self.handle_signal) # StÃ¤ng av alla loopbackar
        signal.signal(signal.SIGHUP, self.handle_signal) # starta om raop discover
        signal.signal(signal.SIGTERM, self.handle_signal) # StÃ¤ng av alla loopbackar
        signal.signal(signal.SIGINT, self.handle_signal)

        #signal management
        self.command_queue = []
        self.signal_event = threading.Event()

    def __del__(self):
        self.kill_all_audio()
        self.led_manager.remove_all_leds()
    
    def __exit__(self):
        self.kill_all_audio()
        self.led_manager.remove_all_leds()
    



    def get_raop_sinks(self, wait_after_restart = False):
        timeout = 1
        sinks = Nodes()
        statuses = []
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
                            status = parts[6]  # Seventh column (sink status)
                            sinks.append(Sink(int(id), name, airplay=True, status= status))  # Create Sink object
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
        else:
            log_message("ERROR: No valid sinks found after waiting. Check PipeWire/PulseAudio!", True, "get_raop_sinks")
        return sinks
    
    def get_next_sink_id(self):
        """Returns the ID of the next available RAOP sink, cycling through them."""
        #refresh sinks
        all_sinks = self.get_raop_sinks()
        
        if not all_sinks:  # If no sinks exist, return None
            return None

        # If no loopback exists, return the first sink
        if not self.loopbacks:
            return all_sinks[0].id #warning, this ID might have changed
        
        #id might have changed, fetch name of sink in loopback
        last_sink_name = self.loopbacks[-1].sink.name

        # Get all sink IDs and names as a list
        sink_ids , sink_names = zip(*[(sink.id, sink.name) for sink in all_sinks])
        

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
        all_sinks = self.get_raop_sinks()
        
        if not all_sinks:  # If no sinks exist, return None
            return None

        # If no loopback exists, return the first sink
        if not self.loopbacks:
            return all_sinks[0].get_canonical_name()
        
        #id might have changed, fetch name of sink in loopback
        last_sink_name = self.loopbacks[-1].sink.name

        # Find index of the last used sink (default to -1 if not found)
        last_index =  all_sinks.get_index_by_name(last_sink_name)

        # Get the next sink in a circular manner
        next_index = (last_index + 1) % len(all_sinks)
        return all_sinks[next_index].get_canonical_name()
    
    def get_prev_sink_name(self):
        """Returns the ID of the next available RAOP sink, cycling through them."""
        #refresh sinks
        all_sinks = self.get_raop_sinks()
        
        if not all_sinks:  # If no sinks exist, return None
            return None

        # If no loopback exists, return the first sink
        if not self.loopbacks:
            return all_sinks[0].get_canonical_name()
        
        #id might have changed, fetch name of sink in loopback
        last_sink_name = self.loopbacks[-1].sink.name

        # Find index of the last used sink (default to -1 if not found)
        last_index =  all_sinks.get_index_by_name(last_sink_name)

        # Get the next sink in a circular manner
        next_index = (last_index - 1) % len(all_sinks)
        return all_sinks[next_index].get_canonical_name()

   
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
    
    def load_os_loopbacks(self):
        #This function loads all loopbacks in the system associated with the standard source!!
        """Returns all loopbacks in the system"""
        result = subprocess.run(["pactl", "list", "modules", "short"], capture_output=True, text=True, check=True)
        result = result.stdout.strip()
        loopbacks = []
        all_sinks = self.get_raop_sinks()
        for line in result.split("\n"):
            if "loopback" in line:
                parts = line.split()
                id = int(parts[0])
                source_id = int(parts[2].split("=")[-1])
                sink_id = int(parts[3].split("=")[-1])

                #check if this is a raop loopback
                sink = all_sinks.get_node_by_id(sink_id)
                if not sink:
                    continue

                #check if source is STNDARD_SOURCE
                source = self.all_sources.get_node_by_id(source_id)
                if not source:
                    continue
                if source.name != STANDARD_SOURCE:
                    #kill loopback
                    log_message(f"Loopback {id} is not using standard source {STANDARD_SOURCE}. Removing loopback.")
                    subprocess.run(["pactl", "unload-module", str(id)], capture_output=True, text=True, check=True)
                    continue
                #create loopback object
                print(f"Loopback {id} found in system. Adding to internal representation.")
                loopbacks.append(Loopback(source, sink, id))
        return loopbacks
        
    
    def switch_audio(self, sink_name):
        all_sinks = self.get_raop_sinks()
        new_sink = all_sinks.is_node_name(sink_name)
        if not new_sink:
            log_message(f"When switching audio sink, Sink {sink_name} not found")
            return
        self.kill_all_audio()
        #create new loopback
        loopback = Loopback(self.current_source, new_sink)
        self.loopbacks.append(loopback)

    def add_audio(self, sink_name):
        all_sinks = self.get_raop_sinks()
        new_sink = all_sinks.is_node_name(sink_name)
        if not new_sink:
            log_message(f"Sink {sink_name} not found", True, "more_audio")
            self.led_manager.flash_error()
            return
        if self.sink_in_loopbacks(sink_name):
            log_message (f"Tried to open already active sink {sink_name}")
        else:
            try:
                loopback = Loopback(self.current_source, new_sink)
                self.loopbacks.append(loopback)
                print(f"add_audio: Created loopback {id(loopback)} for {new_sink.name}")
                log_message (f"Opened sink between {self.current_source} and {new_sink}")
                self.led_manager.flash_ok()
            except subprocess.CalledProcessError as e:
                log_message(f"ERROR: Could not create loopback to {sink_name}: {e}", True, "add_audio")
                self.led_manager.flash_error()
    
    def kill_audio(self, sink_name):
        for loopback in self.loopbacks:
            if loopback.sink.name == sink_name:
                try:
                    #loopback.remove_in_os()
                    loopback.unload()
                    self.loopbacks.remove(loopback)
                    log_message (f"Remove sink {sink_name} from loopback")    
                    self.led_manager.flash_ok_2()
                    return
                except:
                    log_message(f"ERROR: Could not remove sink {sink_name} from loopback", True, "KillAudio")
                    self.led_manager.flash_error()
                    return
        log_message(f"Loopback for sink {sink_name} not found", True, "KillAudio")
    
    def kill_all_audio(self):
        for loopback in self.loopbacks:
            loopback.remove_in_os()
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
                    self.command_queue.append(EventCommand(action="switch", sink_name=next_sink_name))
                else:
                    write_status("ERROR: No valid sink found!")
            
            elif command == "prev":
                prev_sink_name = self.get_prev_sink_name()
                if prev_sink_name:
                    self.command_queue.append(EventCommand(action="switch", sink_name=prev_sink_name))
                else:
                    write_status("ERROR: No valid sink found!")
            
            elif command: #if command is not empty
                #is it part of a sink name?
                all_sinks = self.get_raop_sinks()
                sink = all_sinks.is_node_name(command)
                if sink:
                    #check if sink is already in loopbacks, then kill it
                    if self.sink_in_loopbacks(sink.name):
                        self.command_queue.append(EventCommand(action="kill", sink_name=sink.name))
                    #if not, open a loopback
                    else:
                        self.command_queue.append(EventCommand(action="add", sink_name=sink.name))
                else: 
                    write_status(f"ERROR: Unknown command '{command}'")
                    print(f"Available sinks: ({len(all_sinks)})")
                    for sink in all_sinks:
                        print (sink.name)
                          
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
        def restore_loopbacks():
            #restore loopbacks

            #before killing audio copy loopbacks so we can restore them
            old_loopback_names = [l.sink.canonical_name() for l in self.loopbacks]
            self.kill_all_audio()
            restart_pulseaudio(delete_os_loopbacks=True)
            #reload_module_raop_discover()


            all_sinks = self.get_raop_sinks()
            for canonical_sink_name in old_loopback_names:
                #check if sink is still available
                sink = all_sinks.is_node_name(canonical_sink_name)
                if not sink:
                    log_message(f"Loopback Sink {canonical_sink_name} not found in system. Removing loopback.")
                    continue
                self.add_audio(sink.name)
            return

        

        # se till att ljud tar sig fram till den sink som användaren hade för avsikt att ljudsätta 

        all_sinks = self.get_raop_sinks()
        for loopback in self.loopbacks:
            #check if loopback is still running
            loopback_name = loopback.sink.canonical_name()
            active_sink = all_sinks.is_node_name(loopback_name)
            if not active_sink:
                log_message(f"Loopback Sink {loopback_name} not found in system.")
                log_message(f"See if a restart of pipewire can fix that")
                restore_loopbacks()
                #check if loopback is back
                continue
            else:
                #check if sink is still running
                if active_sink.status != "RUNNING":
                    log_message(f"WARNING: Loopback Sink {loopback_name} is not running.")
                    

        """
        #1. Check if all sinks are still available in PulseAudio and RUNNING. Reload RAOP if not.
        #2. Check if all internal representation of loopbacks are actually running in the system. Kill and remove if not.
        #3. Check if there are more/fewer loopbacks in system than in internal representation. Kill and remove if not.

        os_sinks = self.get_raop_sinks()
        #0 check if a loopback sink has gone missing
        for loopback in self.loopbacks:
            if not os_sinks.is_node_name(loopback.sink.canonical_name()):
                log_message(f"ERROR: Loopback sink {loopback.sink.name} not found in system. Restarting pipewire.", push=True, push_title="AudioRouter.monitor")
                restore_loopbacks()
                return
        
        
        #1. Check if all sinks are still available and RUNNING

        for saved_sink in self.all_sinks:
           os_sink = os_sinks.get_node_by_name(saved_sink.canonical_name())
           if not os_sink:
               #sink does not exist anymore
               log_message(f"WARNING: Sink {saved_sink.canonical_name()} (ID {saved_sink.id}) dissapeared!")
               #restore_loopbacks()
               #return #let's assume everything is working until next monitor cycle
           elif saved_sink.status == "RUNNING" and os_sink.status != "RUNNING":
                #sink status has changed
                log_message(f"WARNING: Sink {saved_sink.name} (ID {saved_sink.id}) status changed from {saved_sink.status} to {os_sink.status}.")
                #restore_loopbacks() kan bero på att apple mutar om det är tysy = normalt
                #return
           
        #2. Check if all internal representation of loopbacks are actually running in the system. Kill and remove if not.

        if len(self.loopbacks) == 0:
            return #no loopbacks to check
        result = subprocess.run(["pactl", "list", "modules", "short"], capture_output=True, text=True, check=True)
        result = result.stdout
        modules = []
        for line in result.split("\n"):
            if "loopback" in line:

                parts = line.split()
                #id = int(parts[0])
                #source = int(parts[2].split("=")[-1])
                sink_id = int(parts[3].split("=")[-1])
                modules.append((sink_id))
        #3. Check if there are more/fewer loopbacks in system than in internal representation. Kill and remove if not.
        if len(modules) != len(self.loopbacks):
            log_message(f"ERROR: Number of loopbacks ({len(modules)}) in system does not match internal representation ({len(self.loopbacks)}). Restarting RAOP.", push=True, push_title="AudioRouter.monitor")
            restore_loopbacks()
            return
        
        for loopback in self.loopbacks:
            if not loopback.sink.id in modules:
                log_message(f"ERROR: Loopback for sink {loopback.sink} not running. Removing loopback.")
                self.kill_audio(loopback.sink.name)
                return
        if len(self.loopbacks) != len(modules):
            log_message("ERROR: Number of loopbacks in system does not match internal representation. Restarting RAOP.", push=True, push_title="AudioRouter.monitor")
            restore_loopbacks()

       """

            
    def run(self):
        while True:
            self.signal_event.wait(timeout=10)

            #Handle all events in the queue that arrived through handle_signal
            while self.command_queue:
                event = self.command_queue.pop(0)
                if event.action == "switch":
                    self.switch_audio(event.sink_name)
                    write_status(f"SUCCESS: Switched to {event.sink_name}")

                elif event.action == "add":
                    self.add_audio(event.sink_name)
                    write_status(f"SUCCESS: Added {event.sink_name} as sound output.")
                    #loop for debugging purposes. remove later
                    for l in self.loopbacks:
                        if l.sink.name == event.sink_name:
                            print (f"pw ids: {l.get_pipewire_ids()}")
                            break
                elif event.action == "kill":
                    self.kill_audio(event.sink_name)
                    write_status(f"SUCCESS: Shut off {event.sink_name}")
                elif event.action == "kill_all":
                    self.kill_all_audio()
                    write_status("SUCCESS: All audio loopbacks shut off")
                elif event.action == "restart": 
                    restart_pulseaudio()
                    write_status("SUCCESS: PulseAudio restarted")
                else:
                    log_message(f"ERROR: Unknown event action {event.action}")
            self.signal_event.clear() #the event has been handled

            self.monitor()
 

###############################################
######### SUPPORT FUNCTIONS ###################
###############################################

RELOAD_LOCK = threading.Lock()  # Create a lock object
RESTART_LOCK = threading.Lock()  # Create a lock object

def reload_module_raop_discover(unload_first= True):
    """Safely reloads module-raop-discover"""
    print("Restarting module-raop-discover...")
    if unload_first:
        os.system("pactl unload-module module-raop-discover")
        time.sleep(2)  # Avoid race conditions
    os.system("pactl load-module module-raop-discover")
    print("RAOP discover restarted.")
    #check if module is loaded
    for i in range(5):
        result = subprocess.run(["pactl", "list", "modules", "short"], capture_output=True, text=True, check=True)
        if "module-raop-discover" in result.stdout:
            print("Module raop-discover loaded successfully.")
            return
        else:
            print(f"Waiting for raop module to load... ({i+1}/5)")
            time.sleep(1)
    print("ERROR: Failed to load module raop-discover.")

def raop_module_loaded ():
    raop_loaded = False
    result = subprocess.run(["pactl", "list", "modules", "short"],capture_output=True, text=True, check=True)
    for line in result.stdout.split("\n"):  # Split into lines
        if "module-raop-discover" in line:
            raop_loaded = True
            log_message ("Raop module is loaded", True, "raop_module_loaded")
            break
    #load raop module
    return raop_loaded

def restart_pulseaudio (delete_os_loopbacks = False):
    try:
        with RELOAD_LOCK:
            if delete_os_loopbacks:
                #delete all loopbacks in os
                log_message("Deleting all RAOP loopbacks")
                result = subprocess.run(["pactl", "list", "modules", "short"], capture_output=True, text=True, check=True)
                for line in result.stdout.split("\n"):
                    if "loopback" in line:
                        parts = line.split()
                        id = int(parts[0])
                        subprocess.run(["pactl", "unload-module", str(id)], capture_output=True, text=True, check=True)
                        log_message(f"pactl: Deleting loopback module {id}")

            log_message("Restarting Pulse Audio and Pipewire")
            subprocess.run (["systemctl" ,"--user", "restart",  "pipewire", "pipewire-pulse"], capture_output=True, text=True, check=True)
            #Stability: make sure raop module is loaded before movin on
            for i in range(5):
                #check if pulse audio is running
                result = subprocess.run(["pactl", "info"], capture_output=True, text=True, check=True)
                log_message ("Pipewire and PulseAudio restarted")
                break
                
            else: 
                log_message ("WARNING: RAOP sinks did not come back in time")

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

def wait_for_pulseaudio(timeout=10):
    start = time.time()
    while True:
        try:
            subprocess.run(["pactl", "info"], check=True, stdout=subprocess.DEVNULL)
            print("PulseAudio is ready!")
            return True
        except subprocess.CalledProcessError:
            if time.time() - start > timeout:
                print("Timeout: PulseAudio not ready.")
                return False
            time.sleep(0.5)

def wait_for_journal():
    try:
        for i in range(5):
            journal.send(MESSAGE=f"Waiting for journal. Attempt {i+1}", SYSLOG_IDENTIFIER="audio-router")
            time.sleep(0.2)
    except Exception as e:
        print(f"Journald not ready: {e}")


##################################################
############ LOGGING & STATUS FUNCTIONS ##########
##################################################
    

LOG_FILE = "/tmp/audio-router.log"

def log_message(message, push=False, push_title = "audio-router"):
    with open(LOG_FILE, "a") as f:
        f.write(f"{message}\n")
    debug_print(message)  # Also print to system logs for debugging
    journal.send(MESSAGE = message, SYSLOG_IDENTIFIER="audio-router") # Write to journald 
    if push or "ERROR" in message.upper():
        send_push (push_title, message)

def debug_print(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)

STATUS_FILE = "/tmp/audio-router-status.log"
def write_status(message):
    """Skriver status om senaste åtgärden
    with open(STATUS_FILE, "w") as f:
        f.write(message + "\n")"""
    log_message(f"{message}", push=True)
    
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
    wait_for_journal()

    PUSHOVER_USER = os.getenv("PUSHOVER_USER")
    PUSHOVER_TOKEN = os.getenv("PUSHOVER_TOKEN")
    DEFAULT_OUTPUT = "Vardagsrum."
    
    wait_for_pactl()
    log_message ("Start audio-router " + str (time.asctime()), push=True)
    router = AudioRouter()
    log_message("PID: " + str(os.getpid()))
    #sink = router.all_sinks.is_node_name(DEFAULT_OUTPUT)
    #router.command_queue.append(EventCommand(action="add", sink_name=sink.name))
    #router.signal_event.set() #wake up monitor thread
    
    router.run()
    
    
    



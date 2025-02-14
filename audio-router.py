
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
import signal
from dataclasses import dataclass

class Loopback:
    def __init__(self, source, sink):
        result = subprocess.run ("pactl", "load-module", "module-loopback", "source=" + source, "sink=" + sink, shell=True)
        self.id = result.stdout.split()[0]
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
                    if node["info"]["props"].get("pulse.module.id") == self.id:
                        node_ids.append(node["id"])
        
        

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
            subprocess.run(["pw-unload", node_id], check=True)
        
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
        self.sink_array.append(node)
    
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
        sinks = Nodes()
        result = subprocess.run(["pactl", "list", "sinks", "short", "|", "grep", "raop"], capture_output=True, text=True, check=True)
        for line in result.stdout:
            id = line.split()[0]
            name = line.split()[1]
            airplay = True
            sinks.append(Sink(id, name, airplay))
        return sinks
    
    def get_next_sink_id(self):
        # Om det inte finns några RAOP-sinkar, returnera None
        if not self.all_sinks:
            return None
        # Hitta vilken sink som används i den senaste loopbacken
        last_sink_id = self.loopbacks[-1].sink if self.loopbacks else 0  # Använd 0 om ingen loopback finns
        # Leta upp indexet för den aktuella sinken i listan
        current_index = 0
        for i, sink in enumerate(self.all_sinks):
            if sink.id == last_sink_id:
                current_index = i
                break  # Stoppa loopen när vi hittar aktuell sink
        # Räkna ut nästa sink genom att gå till nästa index i listan (cirkulär rotation)
        next_index = (current_index + 1) % len(self.all_sinks)
        return self.all_sinks[next_index].id

    
    def get_all_sources(self):
        result = subprocess.run(["pactl", "list", "sources", "short"], capture_output=True, text=True, check=True)
        sources = Nodes()
        for line in result.stdout:
            id = line.split()[0]
            name = line.split()[1]
            if "raop" in name: #skip raop sources
                continue
            sources.append(Node(id, name))
        return sources
    
        
    
    def switch_audio(self, sink_id):
        new_sink = self.all_sinks.get_sink_by_id(sink_id)
        if not new_sink:
            print(f"Sink {sink_id} not found")
            return
        self.kill_all_audio()
        #create new loopback
        loopback = Loopback(self.current_source, new_sink)
        self.loopbacks.append(loopback)

    def more_audio(self, sink_id):
        new_sink = self.all_sinks.get_sink_by_id(sink_id)
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
        if sig == signal.SIGUSR1:
            print("Mottog SIGUSR1 - Växlar ljudutgång")
            self.switch_audio(self.get_next_sink_id())
        elif sig == signal.SIGUSR2:
            print("Mottog SIGUSR2 - Stänger av alla loopback")
            if self.loopbacks:
                self.kill_all_audio()
        elif sig == signal.SIGTERM or sig == signal.SIGINT:
            print("Mottog SIGTERM/SIGINT - Stänger ner allt ljud")
            self.kill_all_audio()
            exit(0)


    
    def monitor(self):
        while True:
            #Check if all sinks are still available
            new_sinks = self.get_raop_sinks()
            for sink in self.all_sinks:
                if not self.all_sinks.get_sink_by_id(sink.id):
                    self.kill_all_audio()
                    reload_module_raop_discover()
                    self.all_sinks = new_sinks
                    break
            #check if sinks are RUNNING
            result = subprocess.run(["pactl", "list", "modules"], capture_output=True, text=True, check=True)
            modules = json.loads(result.stdout)
            for loopback in self.loopbacks:
                for module in modules:
                    if "Arguments" in module:
                        if "sink="&loopback.sink in module["Arguments"]:
                            #check if module is running
                            try:
                                result = subprocess.run(["pactl", "list", "sinks", "short", "|", "grep", loopback.sink], capture_output=True, text=True, check=True)
                                if not result.stdout.strip():
                                    print(f"Sink {loopback.sink} not found")
                                    raise Exception
                                if "RUNNING" not in result.stdout:
                                    print(f"Sink {loopback.sink} not running")
                                    raise Exception
                            except:
                                self.kill_audio(loopback.sink)
                                print(f"Loopback for sink {loopback.sink} not running")
                                break
                                print(f"Killing audio to sink {loopback.sink}")





            signal.pause(10)
         
def reload_module_raop_discover():
    #unload module
    with self.lock:
        print("Restarting module-raop-discover...")
        os.system("pactl unload-module module-raop-discover")
        os.system("sleep 2")
        os.system("pactl load-module module-raop-discover")
        print("RAOP discover restarted.")



router = AudioRouter()
router.monitor()
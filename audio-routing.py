
from dataclasses import dataclass
import os
import subprocess
import json
import time




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
        # Return self to be used within the with block
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



    

def list_raop_sinks ():
    result = subprocess.run ("pactl","list", "sinks", "short", "|", "grep", "raop", shell=True)
    sinks = SinkList()
    for line in result.stdout:
        sink = Sink()
        sink.id = line.split()[0]
        sink.name = line.split()[1]
        sink.airplay = True
        sinks.sinkArray.append(sink)
    return sinks

LIST_OF_SINKS = list_raop_sinks()

####LOOBPACK FUNCTIONS






def switch_audio(sink_id):
    pass

def monitor_audio():
    while True:
        #check if airplay sinks are still available
        sinks = list_raop_sinks()

        time.sleep(10)
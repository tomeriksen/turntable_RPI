
#SUPPORTFUNKTIONER
#KLASSER 
# Loopback - klass som hanterar loopbackar. Brygga mellan pulseaudio och pipewire
# Nodes - klass som hanterar sources / sinks 
# Sinklist - klass som hanterar en lista av sinks.
# Sink - klass som hanterar sinks. Ãrver frÃ¥n Node.
# Source - klass som hanterar sources. Ãrver frÃ¥n Node.
# Node - klass som hanterar en nod.
# AudioRouter - huvudklass som hanterar ljudvÃ¤xlingar.
from dataclasses import dataclass
import subprocess
import os
import json

class Loopback:
    def __init__(self, source, sink, id=None):
        try:
            if not id: # if no id is given, create a new loopback
                result = subprocess.run(
                    ["pactl", "load-module", "module-loopback", f"source={source.id}", f"sink={sink.id}"],
                    capture_output=True, text=True, check=False)
                result = result.stdout.split()
                id = result[0]
            self.id = int(id)
            sink.status = "RUNNING"
            self.source = source
            self.sink = sink
            print(f"Loopback created: {self.id} from {source.name} to {sink.name}")
        except subprocess.CalledProcessError as e:
            print(f"ERROR: Could not create loopback to {sink.name}: {e}")
    
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
                            print(f"Loopback Node ID: {node['id']}, Pulse ID: {module_id}")
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

    #remove loopback from pulseaudio
    def unload(self):
        try:
            # Unload the loopback module using pactl
            result = subprocess.run(["pactl", "unload-module", str(self.id)], capture_output=True, text=True, check=True)
            print(f"Loopback {self.id} removed from PulseAudio.")
        except subprocess.CalledProcessError as e:
            print(f"ERROR: Could not remove loopback {self.id}: {e}")
        self.sink.status = "SUSPENDED"

    #OBSLOTE
    def remove_in_os(self):
        #check if node exists
        def node_exists(node_id: int) -> bool:
        #Check if a PipeWire node with given ID exists.
            try:
                output = subprocess.check_output(["pw-dump"], text=True)
                nodes = json.loads(output)
                return any(obj.get("id") == node_id for obj in nodes)
            except Exception as e:
                print(f"Error checking node existence: {e}")
                return False
        
        # delete the pw loopback modules
        pw_node_ids = self.get_pipewire_ids()
        if not pw_node_ids:
            print(f"No PipeWire nodes found connected to  loopback {self.id}")
        else:
            for pw_node_id in pw_node_ids:
                if node_exists(pw_node_id):
                    try: 
                        subprocess.run(["pw-cli", "destroy", str(pw_node_id)], check=True)
                        print(f"Loopback.remove: Destroyed pw node {pw_node_id} to pa sink {self.sink.name}")
                    except subprocess.CalledProcessError as e:
                        print(f"Loopback.remove: Error destroying pipewire node {pw_node_id}: {e}")
                else:
                    print(f"Pipewire node {pw_node_id} does not exist")
        self.sink.status = "SUSPENDED"
        
    def __enter__(self):
        #return self to be used within the with block
        return self



    
    
@dataclass
class Node:
    id: int
    name: str

@dataclass
class Sink(Node): 
    airplay: bool = True
    status: str = "SUSPENDED"

    def is_running(self,os_sink_status):
        if self.status =="RUNNING":
           return True
        else:
            return False
    
    def canonical_name(self):
        # Return a canonical name for the sink
        parts = self.name.split(".")
        return ".".join(parts[1:3]) if len(parts) > 3 else self.name
    
    def identifier_name(self):
        # Return a identifier name for the sink
        try:
            parts = self.name.split(".")
            return parts[1] if len(parts) > 3 else None
        except IndexError:    
            print(f"Error: Unable to split name '{self.name}' into parts.")
            return None
    
    def __str__(self):
        return f"Sink(id={self.id}, name={self.name}, status={self.status})"
    

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


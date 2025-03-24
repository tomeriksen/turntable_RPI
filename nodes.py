
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
                            print(f"Loopback Node ID: {node['id']}, Module ID: {module_id}")
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
        node_ids = self.get_pipewire_ids()
        for node_id in node_ids:
            if node_exists(node_id):
                try: 
                    subprocess.run(["pw-cli", "destroy", str(node_id)], check=True)
                    print(f"Destroyed node {node_id}")
                except subprocess.CalledProcessError as e:
                    print(f"Error destroying node {node_id}: {e}")
            else:
                print(f"Node {node_id} does not exist")
        
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


# Audio Router – Dokumentation
📌 **Syfte**: Jag ville koppla ihop min vinylspelare med mina Apple Homepods. För det ändamålet har jag skapat denna mjukvara för Raspeberry Pi. Audio Router är en service för Raspberry Pi som som hanterar ljudväxling till Appleplay-enheter som Homepods, aka RAOP-sinks (Remote Audio Output Protocol).  Den hanterar:
* **Sink- och source-listor** genom att hämta och analysera pactl-utdata.
* **Dynamisk ljudväxling** mellan olika ljudenheter.
* **Signalhantering** för externa kontroller via kill -SIGUSR1 och kill -SIGUSR2.
* **Felhantering** och återställning vid förlorade eller ändrade enheter.
* **Automatisk återstart av PulseAudio/PipeWire** vid problem.


⠀
# 1. Systemöversikt
### 🎯 Komponenter
* **Loopback-klasser**: Hanterar loopbacks mellan källor och sinks.
* **Node-hantering**: Strukturerar ljudenheter.
* **Signalhantering**: Gör det möjligt att styra tjänsten via kill-kommandon.
* **PulseAudio/PipeWire-övervakning**: Detekterar och hanterar ljudproblem.
* **Kommandofil** (/tmp/audio-router-command): Används för att skicka instruktioner.
* **Statusfil** (/tmp/audio-router-status.log): Loggar senaste åtgärden.
* **Loggfil** (/tmp/audio-router.log): Samlar debug- och felmeddelanden.

### Hårdvara
* **Rasperry Pi** Jag har teatat den med Rasperry Pi 4, men Raspberry Pi 3 borde också funka
* **Pisound** Mjukvaran är skriven för detta ljudkort som sitter kopplat direkt på bussen.
* **Pisound case** Bra låda om man vill kunna använda Pisounds reglage på ett vettigt sätt.

Audiorouter förlitar sig inte på någon skärm utan är väldigt slimmat.


⠀
# 2. Viktiga Filvägar
| **Fil** | **Funktion** |
|:-:|:-:|
| `/tmp/audio-router.log` | Huvudloggfil för debugging |
| `/tmp/audio-router-status.log` | Loggar den senaste genomförda åtgärden |
| `/tmp/audio-router-command` | Tar emot kommandon från externa program |

# 3. Klassöversikt

### 🔊 Huvudklass: AudioRouter
```
class AudioRouter:
def __init__(self):
```
* **Initierar och konfigurerar ljudsystemet** vid start.
* Om raop_module saknas: **startar om PulseAudio/PipeWire**.
* Laddar in **alla sinks och sources**.
⠀
`⠀def switch_audio(self, sink_name):`
* Byter till en annan RAOP-sink genom att skapa en ny loopback och radera gamla.

`⠀def monitor(self):`
* Kontinuerligt **övervakar sinks och sources** för att hantera bortfall och fel.
* Om en sink försvinner: **laddar om RAOP-discover och försöker återskapa loopbacks**.

⠀
### Node-hantering

```
@dataclass
class Node:
	id: int
	name: str
```
* En generell representation av en ljudnod (sink eller source).

```
@dataclass
class Sink(Node): 
  	airplay: bool = True
```
* **Sink**-klassen är en specialisering av Node och används för att hantera RAOP-ljudutgångar.⠀

```
⠀class Nodes:
    def __init__(self):
        self.node_array = []
```
* Hanterar en lista av Node-objekt.
* Tillåter sökning (get_node_by_id(), get_node_by_name()) och borttagning av noder.

⠀
# 4. Signalhantering
### Hur man skickar kommandon
| **Signal**                                                   | **Funktion**                   |
|:------------------------------------------------------------:|:------------------------------:|
| `kill -SIGUSR1 $(pgrep -f audio-router.py)`                  | Växlar till nästa RAOP-sink    |
| `kill -SIGUSR2 $(pgrep -f audio-router.py)`                  | Startar om PulseAudio/PipeWire |
| `echo "mute" > /tmp/audio-router-command && kill -SIGUSR1 $(pgrep -f audio-router.py)` | Mute/Unmute                    |
| `echo "prev" > /tmp/audio-router-command && kill -SIGUSR1 $(pgrep -f audio-router.py)` | Växlar till föregående sink    |
```
def handle_signal(self, sig, frame):
	command = read_command()
	if sig == signal.SIGUSR1:
		if command == "mute":
			subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
		elif command =="next":
			self.switch_audio(self.get_next_sink_name())
		elif command == "prev":
			self.switch_audio(self.get_prev_sink_name())
		else:
			sink = self.all_sinks.is_node_name(command)
		if sink:
			self.more_audio(sink.name)
```
* Läser in **senaste kommandot** från /tmp/audio-router-command och utför åtgärden.

⠀
# 5. PulseAudio och PipeWire-återställning
Om RAOP-modulen försvinner eller PulseAudio kraschar:
```
def restart_pulseaudio():
	subprocess.run(["systemctl", "--user", "restart", "pipewire", "pipewire-pulse"])
```
* **Startar om PulseAudio och PipeWire**.
* Om raop_module saknas **tvingas en ny laddning** av module-raop-discover.

⠀
# 6. Starta som tjänst
För att köra audio-router.py som en **systemd-tjänst** vid uppstart:
📌 **Skapa service-fil:**
`sudo nano `~/.config/systemd/user/audio-router.service`
📌 **Lägg till:**
```
[Unit]
Description=Audio Router Service
After=pipewire.service pipewire-pulse.service network-online.target
Wants=network-online.target

[Service]
#Environment="XDG_RUNTIME_DIR=/run/user/1000"
#Environment="PULSE_RUNTIME_PATH=/run/user/1000/pulse"
ExecStartPre=/bin/sleep 5
ExecStart=/usr/bin/python3 /home/tomeriksen/development/turntable-rpi/audio-router.py
Restart=always


[Install]
WantedBy=default.target
```
📌 **Starta tjänsten:**
```
sudo systemctl daemon-reload
sudo systemctl enable audio-router.service
sudo systemctl start audio-router.service
```

# 7. Vanliga fel och lösningar
| **Problem** | **Möjlig lösning** |
|:-:|:-:|
| ERROR: No valid sink found! | Kontrollera pactl list sinks short |
| SIGUSR1 does nothing | Se till att audio-router.py körs (pgrep -fl audio-router.py) |
| Duplicate sinks appear | Testa pactl unload-module module-raop-discover |



# 8. Framtida förbättringar
✅ **Smartare felsökning** – Lägg till automatiska tester för att upptäcka ljudproblem.✅ **Webbgränssnitt/API** – Göra tjänsten mer interaktiv med en webbaserad kontrollpanel.✅ **Bättre logghantering** – Möjlighet att aktivera/döda loggning vid behov.

# 🔧 Sammanfattning
* **Audio Router** hanterar RAOP-sinks och möjliggör smidig växling av ljud.
* Styrs via signaler (SIGUSR1, SIGUSR2) och en kommandofil (/tmp/audio-router-command).
* Startar om PulseAudio/PipeWire vid problem och hanterar förlorade sinks automatiskt.
* Är byggt för att köras som en **systemd-tjänst** på Linux.

⠀🚀 **Redo att användas!** 🎶

Detta borde ge dig en **tydlig och strukturerad dokumentation** för projektet. Vill du ha några justeringar? 😊

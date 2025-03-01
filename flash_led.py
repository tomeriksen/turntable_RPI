import subprocess
import time

class FlashLedManager:
    def __init__(self):
        self.led_procs = []
    
    def __exit__(self):
        self.remove_all_leds()
    
    def remove_all_leds(self):
        for led_proc in self.leds_procs:
            led_proc.terminate()
        self.leds_procs = []
    
    def flash_led(self, count=1):
        cmd = f"source /usr/local/pisound/scripts/common/common.sh && flash_leds {count}"
        subprocess.run(["bash", "-c", cmd], shell=True, check=True)

    def flash_error(self):
        self.remove_all_leds()
        self.led_procs.append (subprocess.Popen(["bash", "-c", "while true; do source /usr/local/pisound/scripts/common/common.sh && flash_leds 20; sleep 0.5; done"], shell=True))


    def flash_ok(self):
        #pause all flash procs 
        self.remove_all_leds()

        self.flash_led(7)
        time.sleep(0.3)
        self.flash_led(35)
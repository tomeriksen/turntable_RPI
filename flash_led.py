import subprocess
import time

FLASH_LED_SCRIPT = "/usr/local/bin/flash_pisound_leds.sh"

class FlashLedManager:
    def __init__(self):
        self.led_procs = []
    
    def __exit__(self):
        self.remove_all_leds()
    
    def remove_all_leds(self):
        for led_proc in self.led_procs:
            led_proc.terminate()
        self.led_procs = []
    
    def flash_led(self, count=1):
        cmd =  f"{FLASH_LED_SCRIPT} {count}"
        try:
            subprocess.run(cmd, shell=True, check=True, timeout = 2)
        except subprocess.TimeoutExpired:
            print("Timeout: flash_leds hängde sig!")

    def flash_error(self):
        self.remove_all_leds()
        self.led_procs.append (subprocess.Popen(["bash", "-c", "while true; do source /usr/local/pisound/scripts/common/common.sh && flash_leds 20; sleep 0.5; done"], shell=True))


    def flash_ok(self):
        #pause all flash procs 
        self.remove_all_leds()

        self.flash_led(7)
        time.sleep(0.3)
        self.flash_led(35)
    
    #a longer flash used when completeing opposite action
    #for example: when removing a loopback
    def flash_ok_2(self):
        #pause all flash procs 
        self.remove_all_leds()

        self.flash_led(35)
        time.sleep(0.3)
        self.flash_led(7)
        time.sleep(0.3)
        self.flash_led(7)
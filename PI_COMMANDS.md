# Pi Commands Reference

## Activation
```bash
source ~/markov-env/bin/activate
```

## Venv Setup (from scratch)

### 1. Create venv
```bash
python3 -m venv ~/markov-env
```

### 2. Activate & upgrade pip
```bash
source ~/markov-env/bin/activate
pip install --upgrade pip
```

### 3. Install Python packages
```bash
pip install Pillow evdev spidev lgpio gpiozero
```

### 4. Install system packages (required for GPIO on Python 3.13+)
```bash
sudo apt install liblgpio-dev swig python3-dev
```

### 5. Install Waveshare e-paper library (from GitHub, NOT pip)
```bash
cd ~
git clone https://github.com/waveshare/e-Paper.git
cd e-Paper/RaspberryPi_JetsonNano/python
pip install .
```

### Combined: complete setup (run these one by one)
```bash
python3 -m venv ~/markov-env
source ~/markov-env/bin/activate
pip install --upgrade pip
sudo apt install liblgpio-dev swig python3-dev
pip install Pillow evdev spidev lgpio gpiozero
cd ~ && git clone https://github.com/waveshare/e-Paper.git
cd e-Paper/RaspberryPi_JetsonNano/python && pip install .
```

### Check what's installed
```bash
pip list 2>/dev/null | grep -iE 'lgpio|gpiozero|waveshare|pillow|spidev'
```

## E-Paper Display (V2, 800x480)

### Test display
```bash
sudo ~/markov-env/bin/python -c "
from waveshare_epd import epd7in5_V2 as epd
e = epd.EPD()
e.init()
e.Clear()
print('E-paper OK!')
e.sleep()
"
```

### Init step-by-step (find where it hangs)
```bash
sudo ~/markov-env/bin/python -c "
from waveshare_epd import epd7in5_V2 as epd
print('1 import OK')
e = epd.EPD()
print('2 EPD() OK')
e.init()
print('3 init() OK')
e.Clear()
print('4 Clear() OK')
e.sleep()
"
```

### Uninstall broken pip package & install from GitHub
```bash
pip uninstall waveshare-epd -y
cd ~
git clone https://github.com/waveshare/e-Paper.git
cd e-Paper/RaspberryPi_JetsonNano/python
pip install .
```

### Fix display not refreshing after first Clear
Call `e.init()` before every `e.display()`. In `pi_client.py`:
```python
def display_scene(epd, png_bytes: bytes):
    ...
    epd.init()            # <-- add this before display
    epd.display(epd.getbuffer(img))
```

### Fix display not refreshing after first Clear
In `pi_client.py`: call `epd.init()` before each `epd.display()` call.

## GPIO Debug

### Test if header pins are making contact
```bash
sudo ~/markov-env/bin/python -c "
import RPi.GPIO as GPIO, time
GPIO.setmode(GPIO.BCM)
failed = []
for name, pin in [('RST',17),('DC',25),('CS',8),('BUSY',24),('SDA',2),('SCL',3),('GPIO4',4),('GPIO5',5),('GPIO6',6),('GPIO12',12),('GPIO13',13),('GPIO19',19),('GPIO20',20),('GPIO21',21),('GPIO22',22),('GPIO23',23),('GPIO26',26),('GPIO27',27)]:
    try:
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(0.01)
        GPIO.output(pin, GPIO.LOW)
        print(f'{name}(GPIO{pin}) OK')
    except Exception as e:
        print(f'{name}(GPIO{pin}) FAIL: {e}')
        failed.append(name)
GPIO.cleanup()
if failed:
    print(f'FAILED pins: {failed}')
else:
    print('All tested pins OK')
"
```

### Test individual e-paper pins
```bash
sudo ~/markov-env/bin/python -c "
import RPi.GPIO as GPIO, time
GPIO.setmode(GPIO.BCM)
for name, pin in [('RST',17),('DC',25),('CS',8),('BUSY',24)]:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.HIGH)
    time.sleep(0.1)
    GPIO.output(pin, GPIO.LOW)
    print(f'{name}(GPIO{pin}) OK')
GPIO.cleanup()
"
```

## Python Tips

### Exit the Python interactive shell (when you type `python` by mistake)
```bash
exit()
```
Or press **Ctrl+D**.

## System Setup

### Enable SPI
```bash
sudo raspi-config nonint do_spi 0
sudo reboot
```

### Install GPIO dependencies (Python 3.13+)
```bash
sudo apt install liblgpio-dev swig python3-dev
pip install lgpio gpiozero spidev Pillow evdev
```

### Pi Zero USB host mode (for Digispark)
```bash
echo "dtoverlay=dwc2,dr_mode=host" | sudo tee -a /boot/firmware/config.txt
sudo reboot
```
Verify: `cat /sys/kernel/debug/dwc_otg/mode` should say `host`.

```
dtoverlay=dwc2,dr_mode=host
dtoverlay=dwc2,dr_mode=host
```

## Run the Client

### With stdin (keyboard input for A/B)
```bash
sudo ~/markov-env/bin/python ~/pi_client.py 192.168.178.27 9999 --stdin
```

### With Digispark (auto-detect)
```bash
sudo ~/markov-env/bin/python ~/pi_client.py 192.168.178.27 9999
```

### Upload client file from PC

#### Method 1: SCP (small files, one-off)
From Windows (PowerShell in prototype dir):
```powershell
scp pi_client.py pi@192.168.178.XX:~/pi_client.py
```

#### Method 2: HTTP file server (best for rapid iteration)
Start HTTP server on Windows (MUST be in prototype dir):
```powershell
cd C:\Projecten\MultiMarkovPlay\prototype
python -m http.server 8000
```
Then fetch from Pi:
```bash
wget -O ~/pi_client.py http://192.168.178.27:8000/pi_client.py
```

### Digispark evdev debug (check VID/PID match)
```bash
sudo ~/markov-env/bin/python -c "
from evdev import InputDevice, list_devices
for p in list_devices():
    d = InputDevice(p)
    print(hex(d.info.vendor), hex(d.info.product), d.name, d.path)
for p in list_devices():
    d = InputDevice(p)
    if d.info.vendor == 0x16C0 and d.info.product == 0x27DB:
        print('MATCH:', d.path, d.name)
    d.close()
"
```

## Digispark Debug — CRITICAL

### CRITICAL: Digispark VID/PID
| State | VID:PID | Name |
|-------|---------|------|
| Bootloader (5 sec after plug) | `16d0:0753` | `Digistump Digispark` |
| **Running sketch** (what we use) | **`16c0:27db`** | **`digistump.com DigiKey`** |

The `pi_client.py` uses `0x16C0:0x27DB` (the running-sketch VID/PID). The bootloader PID only appears for ~5 seconds and is NOT what we match.

### CRITICAL: Pi Zero OTG — Digispark stroom & dwc2 overlay

**Twee mogelijke oorzaken als Digispark niet verschijnt op `lsusb`:**

**1. `dwc2` overlay niet correct geladen**
```bash
cat /sys/kernel/debug/dwc_otg/mode
```
Moet `host` zijn. Zo niet:
```bash
echo "dtoverlay=dwc2,dr_mode=host" | sudo tee -a /boot/firmware/config.txt
sudo reboot
```
**Belangrijk:** soms werkt het pas na **een tweede reboot**. Eerste reboot laadt de overlay niet altijd correct.

Na correct laden zou de Digispark **direct** (zonder hub) moeten werken.

**2. OTG power — USB hub als fix**
Soms is de inrush current van de Digispark's 68µF bootloader cap te hoog voor de Pi Zero's 5V rail → brownout/crash. Een standaard **non-powered USB hub** ertussen lost dit op (decoupling caps in de hub bufferen de piek). **Let op:** na 1x aansluiten via hub kan de cap al geladen zijn en werkt ie ook direct — maar na een lange stroomloze tijd kan de piek terugkomen.

**Dus:** probeer eerst **zonder hub** (na reboot met correcte overlay). Als dat faalt (crash of geen device), gebruik dan een non-powered USB hub.

### CRITICAL: Firmware must be flashed before troubleshooting
If the Digispark shows as `16d0:0753` Digistump Digispark in `lsusb`, it means only the bootloader is running — no firmware is flashed. The sketch must be flashed first (via Arduino IDE, micronucleus, etc.) before the Digispark will work as a keyboard.

### Check if USB sees the Digispark
```bash
lsusb
```
Expected output (after flashing, with running sketch): `Bus XXX Device XXX: ID 16c0:27db Van Ooijen Technische Informatica Keyboard`

### Catch 5-second bootloader window
```bash
while true; do lsusb; sleep 0.3; done
```

### List all evdev input devices
```bash
sudo ~/markov-env/bin/python -c "
from evdev import InputDevice, list_devices
for p in list_devices():
    d = InputDevice(p)
    print(hex(d.info.vendor), hex(d.info.product), d.name, d.path)
"
```

### Check USB dmesg errors
```bash
dmesg | grep -i -E 'usb|hid|digi|16c0'
```

## SSH

### Connect
```bash
ssh pi@192.168.178.XX
```

### Windows: clear host key (if host identification changed)
```powershell
ssh-keygen -R 192.168.178.XX
```

### Find Pi on network
```bash
# From Pi with monitor:
hostname -I

# From Windows:
arp -a | findstr 192.168.178
```

## Server (Windows, in prototype dir)
```powershell
python main.py --server
```

## Pi List
| Hostname | IP | Model | Notes |
|----------|----|-------|-------|
| pi0 | 192.168.178.45 (was) / .47 (now) | Pi Zero / Pi Zero W | V2 e-paper on HAT, USB OTG |
| pi2 | 192.168.178.46 | Pi 3 A+ | Has soldered header, working SPI |


### Venv Debug
Try creating without pip first, then install pip manually:

python3 -m venv --without-pip ~/markov-env
source ~/markov-env/bin/activate
If that works, install pip manually:

wget https://bootstrap.pypa.io/get-pip.py
python get-pip.py
rm get-pip.py
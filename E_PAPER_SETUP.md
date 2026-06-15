# E-Paper Setup Workflow (Pi 3 / Pi Zero)

## 1. Enable SPI + Reboot
```bash
sudo raspi-config nonint do_spi 0
sudo reboot
```

Verify after reboot:
```bash
ls /dev/spidev*
```
Should show `spidev0.0` and `spidev0.1`.

## 2. Create venv & install base deps
```bash
python3 -m venv ~/markov-env
source ~/markov-env/bin/activate
pip install --upgrade pip
pip install Pillow evdev spidev
```

## 3. System packages for GPIO (required for Python 3.13+)
```bash
sudo apt install liblgpio-dev swig python3-dev
```

## 4. Install GPIO backends
```bash
source ~/markov-env/bin/activate
pip install lgpio
pip install gpiozero
```

## 5. Install Waveshare e-paper library (from GitHub, NOT pip)
```bash
cd ~
git clone https://github.com/waveshare/e-Paper.git
cd e-Paper/RaspberryPi_JetsonNano/python
pip install .
```

## 6. Verify display works (V2 = 800x480)
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

For V1 (640x384), replace `epd7in5_V2` with `epd7in5`.

## 7. Upload & run pi_client.py
```bash
cd ~
wget http://192.168.178.27:8000/pi_client.py
sudo ~/markov-env/bin/python ~/pi_client.py 192.168.178.27 9999 --stdin
```

## Troubleshooting

### "cannot find -llgpio" when installing lgpio
Fix: `sudo apt install liblgpio-dev`

### "No module named 'gpiozero'"
The GitHub Waveshare library depends on gpiozero, not RPi.GPIO directly.
Fix: `pip install gpiozero` + install a backend (`lgpio` for Python 3.13+)

### "PinFactoryFallback" warnings
Normal if lgpio is the only backend installed — gpiozero will use it once lgpio is available.

### Import mismatch led to hang
If the display is V2 (800x480) but pi_client.py imports `epd7in5` (V1), init hangs silently.
Fix: update pi_client.py to import the correct driver (line 37-39).

### USB no power / error -71 on Pi
Pi USB port underpowered for Digispark.
Fix: use a powered USB hub, or wire buttons directly to GPIO (HAT uses all pins, so this requires a stacking header or alternative approach).

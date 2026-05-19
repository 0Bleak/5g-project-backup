sudo bash -c 'cat > /usr/local/bin/connect-5g.sh << "EOF"
#!/bin/bash
echo "[1/6] Stopping ModemManager..."
systemctl stop ModemManager 2>/dev/null

echo "[2/6] Finding modem..."
MODEM_PATH=$(grep -rl "2c7c" /sys/bus/usb/devices/*/idVendor 2>/dev/null | head -1 | xargs dirname)
if [ -z "$MODEM_PATH" ]; then
    echo "ERROR: No Quectel modem found. Plug it in first."
    exit 1
fi
DEV=$(basename $MODEM_PATH)
echo "    Modem at $DEV"

echo "[3/6] Unbinding and reloading drivers..."
echo "$DEV" > /sys/bus/usb/drivers/usb/unbind 2>/dev/null
sleep 2
modprobe -r option 2>/dev/null
sleep 2
modprobe cdc_ether
sleep 2
echo "$DEV" > /sys/bus/usb/drivers/usb/bind 2>/dev/null
sleep 5

echo "    Checking interfaces..."
ls /sys/class/net/

if ! ls /sys/class/net/usb2 > /dev/null 2>&1; then
    echo "    usb2 not found, retrying bind..."
    echo "$DEV" > /sys/bus/usb/drivers/usb/unbind 2>/dev/null
    sleep 2
    echo "$DEV" > /sys/bus/usb/drivers/usb/bind 2>/dev/null
    sleep 5
fi

if ! ls /sys/class/net/usb2 > /dev/null 2>&1; then
    echo "ERROR: usb2 still not found"
    dmesg | grep -i "cdc_ether\|option" | tail -10
    exit 1
fi
echo "    usb2 interface ready"

echo "[4/6] Loading option driver for AT ports..."
modprobe option 2>/dev/null
sleep 2

echo "[5/6] Getting DHCP lease (no default route)..."
rm -f /var/lib/dhcp/dhclient*
ip addr flush dev usb2 2>/dev/null
if [ -f /etc/dhcp/dhclient-usb2.conf ]; then
    dhclient -v -1 -cf /etc/dhcp/dhclient-usb2.conf usb2 2>&1
else
    dhclient -v -1 usb2 2>&1
    ip route del default via 192.168.225.1 2>/dev/null
    ip route del default dev usb2 2>/dev/null
fi

echo "[6/6] Adding route and testing..."
ip route add 10.45.0.0/16 dev usb2 2>/dev/null
ping -I usb2 -c 2 -W 3 10.45.0.1
if [ $? -eq 0 ]; then
    echo "SUCCESS: 5G connected"
else
    echo "WARNING: ping failed but modem may still be registering"
fi
EOF
chmod +x /usr/local/bin/connect-5g.sh'

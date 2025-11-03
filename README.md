# Raspberry Pi HomeServer 🚀

This repo sets up Docker, Apache reverse proxy, Pi-hole, Home Assistant, and a local Streamlit health dashboard on Raspberry Pi.


## Setup

```sh
./setup.sh
```

# To Set Pi-hole Password:
```sh
docker exec -it pihole pihole setpassword 'your_new_password'
```

# To allow iCloudPrivateRelay, set this in ₹/etc/pihole/pihole.toml₹ :
```toml
    # Should Pi-hole always reply with NXDOMAIN to A and AAAA queries of mask.icloud.com
    # and mask-h2.icloud.com to disable Apple's iCloud Private Relay to prevent Apple
    # devices from bypassing Pi-hole?
    #
    # This follows the recommendation on
    # https://developer.apple.com/support/prepare-your-network-for-icloud-private-relay
    #
    # Allowed values are:
    #     true or false
    iCloudPrivateRelay = false ### CHANGED, default = true
```
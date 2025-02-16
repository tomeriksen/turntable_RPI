#!/bin/bash

echo "Söker efter alla PulseAudio loopback-moduler..."

# Hitta alla PulseAudio module-loopback ID:n och ta bort #
PA_MODULE_IDS=$(pactl list modules | grep -B 1 "module-loopback" | grep "Module #" | awk '{print $2}' | tr -d '#')

if [[ -z "$PA_MODULE_IDS" ]]; then
    echo "Inga loopback-moduler hittades i PulseAudio."
    exit 1
fi

echo "Hittade följande PulseAudio loopback-moduler: $PA_MODULE_IDS"

# Loopa igenom varje modul och hitta motsvarande PipeWire-noder
for PA_MODULE_ID in $PA_MODULE_IDS; do
    echo "Behandlar PulseAudio-modul ID: $PA_MODULE_ID"

    NODE_IDS=$(pw-dump | awk -v mod_id="$PA_MODULE_ID" '
        /"pulse.module.id":/ {
            if ($2 == mod_id ",") found=1;
        }
        /"id":/ && found {
            print $2;
            found=0;
        }' | tr -d ',')
        
    if [[ -z "$NODE_IDS" ]]; then
        echo "Ingen PipeWire-nod hittades för PulseAudio-modul $PA_MODULE_ID"
        continue
    fi

    # Ta bort varje hittad PipeWire-nod
    for NODE_ID in $NODE_IDS; do
        echo "Tar bort PipeWire-nod med ID: $NODE_ID"
        pw-cli destroy "$NODE_ID"
    done

    echo "Alla PipeWire-noder kopplade till PulseAudio-modul $PA_MODULE_ID har raderats."

    # Avlasta PulseAudio-modulen
    echo "Avladdar PulseAudio-modul ID: $PA_MODULE_ID"
    pactl unload-module "$PA_MODULE_ID"
done

echo "Alla loopback-moduler och motsvarande PipeWire-noder har raderats!"

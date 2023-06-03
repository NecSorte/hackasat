import os
import time
import numpy as np
import ray
from ray.rllib import agents
from pexpect import spawn, EOF

# Constants
AZIMUTH_RANGE = (160, 6400)
ELEVATION_RANGE = (650, 1450)
MAC_ADDRESS = 'xx:xx:xx:xx:xx:xx'  # replace with the target MAC address
INTERFACE = 'wlan0'  # replace with the actual interface

class AntennaEnv(ray.rllib.env.MultiAgentEnv):
    def __init__(self, config):
        self.azim = np.random.randint(*AZIMUTH_RANGE)
        self.elev = np.random.randint(*ELEVATION_RANGE)
        self.signal_strength = self.get_signal_strength()
        self.command_child = spawn('bash')
        self.command_child.expect(EOF)

    def get_signal_strength(self):
        os.system(f"iwlist {INTERFACE} scan | grep -A 5 -B 5 '{MAC_ADDRESS}' > scan.txt")
        with open("scan.txt") as f:
            for line in f:
                if "Quality" in line:
                    # assuming signal quality format as 'Quality=XX/100'
                    return int(line.split("=")[1].split('/')[0])
        return 0

    def set_antenna(self, azim, elev):
        self.command_child.sendline(f'/send_commands azim {azim}')
        self.command_child.sendline(f'/send_commands elev {elev}')
        self.command_child.expect(EOF)

    def reset(self):
        self.azim = np.random.randint(*AZIMUTH_RANGE)
        self.elev = np.random.randint(*ELEVATION_RANGE)
        self.set_antenna(self.azim, self.elev)
        self.signal_strength = self.get_signal_strength()
        return [self.azim, self.elev, self.signal_strength]

    def step(self, action):
        self.azim += action[0]
        self.elev += action[1]
        self.set_antenna(self.azim, self.elev)
        time.sleep(1)  # wait for antenna to set and for scanning

        new_signal_strength = self.get_signal_strength()
        reward = new_signal_strength - self.signal_strength
        self.signal_strength = new_signal_strength

        return [self.azim, self.elev, self.signal_strength], reward, False, {}


ray.init()
trainer = agents.ppo.PPOTrainer(env=AntennaEnv, config={"framework": "torch"})

# Load from checkpoint if exists
checkpoint_path = "./checkpoint"  # Put your desired checkpoint path here
if os.path.exists(checkpoint_path):
    trainer.restore(checkpoint_path)

# Training loop
for i in range(10000):
    trainer.train()
    if i % 100 == 0:
        checkpoint = trainer.save(checkpoint_path)
        print(f"Checkpoint saved at {checkpoint}")

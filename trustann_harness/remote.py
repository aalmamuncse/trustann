import shlex
import subprocess
import time

class SSH:
    def __init__(self, user, key, timeout=10):
        self.user = user
        self.key = key
        self.timeout = timeout

    def run(self, host, command, check=True, timeout=None):
        cmd = [
            "ssh", "-o", "BatchMode=yes",
            "-o", f"ConnectTimeout={self.timeout}",
            "-o", "StrictHostKeyChecking=accept-new",
            "-i", self.key,
            f"{self.user}@{host}", command
        ]
        p = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
        if check and p.returncode != 0:
            raise RuntimeError(
                f"SSH failed on {host} (rc={p.returncode})\n"
                f"CMD: {command}\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}"
            )
        return p

    def background(self, host, command, log_file):
        q = shlex.quote(command)
        l = shlex.quote(log_file)
        wrapped = f"nohup bash -lc {q} > {l} 2>&1 < /dev/null & echo $!"
        return self.run(host, wrapped).stdout.strip()

    def wait(self, seconds):
        time.sleep(seconds)

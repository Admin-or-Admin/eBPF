#!/usr/bin/env python3
import subprocess
import json
import sys
import argparse
import signal
import os
from datetime import datetime

# --- Aurora Shared Imports ---
from shared.kafka_client import AuroraProducer
from shared.logger import setup_logger

# Initialize structured logging
logger = setup_logger("ebpf-ingestor")

# UI Constants
RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
CYAN, GREEN, RED = "\033[96m", "\033[92m", "\033[91m"

def parse_args():
    parser = argparse.ArgumentParser(description="Aurora eBPF Ingestor")
    parser.add_argument(
        "--brokers", 
        default=os.getenv("KAFKA_BROKERS", "kafka:9092"),
        help="Kafka broker list"
    )
    parser.add_argument("--socket", default="unix:///var/run/tetragon/tetragon.sock")
    parser.add_argument("--no-console", action="store_true", help="Disable console printing")
    return parser.parse_args()

def handle_event(raw_json: str, producer: AuroraProducer, quiet: bool):
    """Parses Tetragon JSON and forwards to Kafka."""
    try:
        event = json.loads(raw_json)
        
        # 1. Forward to Kafka topic: ebpf.raw
        # Uses trace.id or id as the Kafka key for partition affinity if available
        producer.send_log("ebpf.raw", event)
        
        # 2. Local Visibility
        if not quiet:
            ts = event.get("time", "")[11:19]
            # Detect event type for a simple console summary
            etype = next((k for k in ["process_exec", "process_exit", "process_kprobe"] if k in event), "other")
            print(f"{DIM}[{ts}]{RESET} {GREEN}→{RESET} {BOLD}ebpf.raw{RESET} | {etype}")

    except json.JSONDecodeError:
        logger.error(f"Malformed JSON from Tetragon: {raw_json[:100]}")
    except Exception as e:
        logger.error(f"Failed to forward event: {e}")

def stream_events():
    args = parse_args()

    # Initialize Aurora Kafka Producer
    logger.info(f"Connecting to Kafka: {args.brokers}")
    producer = AuroraProducer(bootstrap_servers=[args.brokers])
    
    # Ensure the destination topic exists
    producer.ensure_topic("ebpf.raw", partitions=3, replication=1)

    cmd = ["tetra", "--server-address", args.socket, "getevents"]
    
    try:
        # Launch Tetragon stream
        proc = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True, 
            bufsize=1
        )

        def _shutdown(sig, frame):
            logger.info("Shutting down eBPF ingestor...")
            producer.flush() # Ensure all events are sent before exiting
            producer.close()
            proc.terminate()
            sys.exit(0)

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        print(f"{BOLD}{CYAN}Aurora eBPF Adapter: Local Stream → Kafka (ebpf.raw){RESET}\n")

        for line in proc.stdout:
            clean_line = line.strip()
            if clean_line:
                handle_event(clean_line, producer, args.no_console)

    except FileNotFoundError:
        logger.critical("The 'tetra' CLI was not found in PATH.")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Critical ingestor failure: {e}")
        sys.exit(1)

if __name__ == "__main__":
    stream_events()

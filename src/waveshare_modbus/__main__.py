"""Entry point for waveshare-modbus tool."""

import argparse


def main():
    parser = argparse.ArgumentParser(description="Waveshare Modbus Relay Controller")
    parser.add_argument("--headless", action="store_true", help="Run API server without GUI")
    parser.add_argument("--relay-host", default="192.168.0.81")
    parser.add_argument("--relay-port", type=int, default=4196)
    parser.add_argument("--relay-unit", type=int, default=1)
    parser.add_argument("--api-host", default="0.0.0.0")
    parser.add_argument("--api-port", type=int, default=8001)
    args = parser.parse_args()

    if args.headless:
        _run_headless(args)
    else:
        from .gui import run
        run()


def _run_headless(args):
    import uvicorn
    from .modbus_client import ModbusClient
    from .api import create_api

    client = ModbusClient(host=args.relay_host, port=args.relay_port, unit_id=args.relay_unit)

    try:
        client.connect()
        print(f"Connected to relay device at {args.relay_host}:{args.relay_port}")
    except Exception as e:
        print(f"Warning: could not connect to relay device: {e}")
        print("API will start anyway — call POST /api/connect to connect later")

    app = create_api(client, log_callback=lambda msg: print(msg))
    print(f"API server running at http://{args.api_host}:{args.api_port}")
    print(f"Docs at http://localhost:{args.api_port}/docs")
    uvicorn.run(app, host=args.api_host, port=args.api_port)


if __name__ == "__main__":
    main()

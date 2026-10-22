"""Run the URLovingly server.

    python run.py --dev     local development (mock payments, developer sign-in)
    python run.py           production settings (needs RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET)
"""
import argparse
import os

parser = argparse.ArgumentParser()
parser.add_argument("--dev", action="store_true", help="development mode with mock payments and developer sign-in")
parser.add_argument("--host", default="127.0.0.1")
parser.add_argument("--port", type=int, default=5000)
args = parser.parse_args()

if args.dev:
    os.environ["URLOVINGLY_ENV"] = "development"

from server import create_app  # noqa: E402  (after the environment is configured)

app = create_app()

if __name__ == "__main__":
    app.run(host=args.host, port=args.port, debug=False)

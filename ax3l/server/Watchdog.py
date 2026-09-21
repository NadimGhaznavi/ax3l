import argparse
import logging
import time

from ax3l.activity.CheckServices import CheckServices

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ax3l-unit", required=True)
    parser.add_argument("--llm-unit", required=True)
    parser.add_argument("--report-unit", required=True)
    parser.add_argument("--llm-health-url", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    checker = CheckServices()
    while True:
        checker.run(args.ax3l_unit, args.llm_unit, args.report_unit, args.llm_health_url)
        time.sleep(10)

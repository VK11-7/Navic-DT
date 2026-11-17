def decide(o1,o2):
    # Illustrative decision support only; not a certified HPL/VPL calculation.
    threat=o2["class_name"]; conf=o2["confidence"]; proxy=o1["forecast"]
    if threat=="Spoofing" and conf>=0.70: action="EXCLUDE_SIMULATED_SIGNAL"
    elif threat=="Multipath" and conf>=0.70: action="DOWNWEIGHT_SIMULATED_SIGNAL"
    elif proxy>=0.5: action="MONITOR_AND_ADAPT_SELECTION"
    else: action="RETAIN_WITH_MONITORING"
    return {"action":action,"forecast_proxy":proxy,"threat":threat,"confidence":conf,
            "note":"Proxy-based decision support; not certified GNSS integrity or HPL/VPL."}

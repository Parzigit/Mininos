import sys
import os
import logging

# Ensure current dir is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from real_dlbmt_engine import RealDLBMTEngine

def test_topology_loading():
    logging.basicConfig(level=logging.ERROR)
    
    print("Testing Atlanta Topology loading...")
    try:
        engine = RealDLBMTEngine(topology_name="atlanta")
        print(f"  Controllers: {len(engine.controllers)} (Expected 3)")
        print(f"  Switches: {len(engine.switches)} (Expected 15)")
        print(f"  Links: {len(engine.infra_links)} (Expected 22)")
        
        assert len(engine.controllers) == 3
        assert len(engine.switches) == 15
        assert len(engine.infra_links) == 22
        print("  PASS")
    except Exception as e:
        print(f"  FAIL: {e}")
        import traceback
        traceback.print_exc()

    print("\nTesting Interroute Topology loading...")
    try:
        engine = RealDLBMTEngine(topology_name="interroute")
        print(f"  Controllers: {len(engine.controllers)} (Expected 7)")
        print(f"  Switches: {len(engine.switches)} (Expected 110)")
        print(f"  Links: {len(engine.infra_links)} (Expected 159)")
        
        assert len(engine.controllers) == 7
        assert len(engine.switches) == 110
        assert len(engine.infra_links) == 159
        print("  PASS")
    except Exception as e:
        print(f"  FAIL: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_topology_loading()

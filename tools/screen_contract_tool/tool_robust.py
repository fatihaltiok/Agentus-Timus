# Robust execute_action_plan fix
def execute_action_plan_robust(plan_dict):
    """ROBUST VERSION - Handles missing keys gracefully"""
    try:
        # Input validation
        if not plan_dict or not isinstance(plan_dict, dict):
            return {"error": "Invalid plan_dict", "code": -32001}
        
        steps_data = plan_dict.get("steps", [])
        if not steps_data:
            return {"error": "No steps in plan", "code": -32003}
        
        # Parse steps with flexible key access
        steps = []
        for i, step_data in enumerate(steps_data):
            if not isinstance(step_data, dict):
                continue
                
            # Flexible key access
            op = (step_data.get("op") or 
                  step_data.get("action") or 
                  step_data.get("type", "click"))
                  
            target = (step_data.get("target") or 
                     step_data.get("element") or 
                     step_data.get("selector", ""))
            
            steps.append({
                "op": op,
                "target": target,
                "params": step_data.get("params", {}),
                "retries": step_data.get("retries", 2),
                "timeout_ms": step_data.get("timeout_ms", 5000)
            })
        
        if not steps:
            return {"error": "No valid steps parsed", "code": -32005}
        
        return {"success": True, "steps_count": len(steps), "steps": steps}
        
    except Exception as e:
        return {"error": str(e), "code": -32000}

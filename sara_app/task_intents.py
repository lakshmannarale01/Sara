"""Explicit local task metadata, without guessing dates from ambiguous prose."""
import re

def plan_task(message):
    match=re.fullmatch(r'(?:add\s+|create\s+)?(high|medium|low)\s+priority\s+task\s+(.+)',message.strip(),re.I)
    shopping=re.fullmatch(r'add to (?:my |the )?shopping list\s+(.+)',message.strip(),re.I)
    if not match and not shopping: return None
    text=match.group(2).strip() if match else shopping.group(1).strip()
    priority=match.group(1).lower() if match else 'medium'
    return {'reply':'यह task save करने के लिए तैयार है। Details देख लो।','provider':'task-planner','requires_confirmation':True,
            'action':{'type':'create_task','text':text,'priority':priority,'category':'shopping' if shopping else 'general','label':'Save task'}}

"""Rendering options shared by released Unreal launch profiles."""


def without_hud(arguments):
    """Disable the engine HUD before capture; leave the scene pixels intact."""
    result, commands = [], []
    for argument in arguments:
        if argument.lower().startswith('-execcmds='):
            commands.extend(argument.split('=', 1)[1].split(','))
        else:
            result.append(argument)
    hide = 'set HUD bShowHUD false'
    verify = 'getall HUD bShowHUD'
    commands = [c for c in commands if c.strip().lower() not in {hide.lower(), verify.lower()}]
    result.append('-ExecCmds=' + ','.join([*commands, hide, verify]))
    return result

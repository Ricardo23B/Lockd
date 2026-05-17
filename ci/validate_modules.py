import yaml, sys

with open('modules/modules.yaml') as f:
    data = yaml.safe_load(f)

modules = data.get('modules', [])
required = ['id', 'name', 'description', 'category', 'enable_script', 'check_script']
errors = []

for m in modules:
    for field in required:
        if field not in m:
            errors.append(m.get('id', '?') + ' falta campo: ' + field)

if errors:
    for e in errors:
        print('ERROR: ' + e)
    sys.exit(1)

print('OK — ' + str(len(modules)) + ' modulos validados.')
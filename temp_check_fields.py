import json

# 检查所有 review 文件中是否有 spec.cpu_cores 和 spec.memory_gb 的字段
review_dir = 'database/review'

print("检查 spec.cpu_cores, spec.memory_gb, spec.storage_gb 字段使用情况：")
found = False
for i in range(1, 21):
    num = f'{i:02d}'
    r_file = f'{review_dir}/group-{num}.review.json'

    with open(r_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for item in data:
        for field in item.get('not_match_field', []):
            fk = field.get('field_key')
            if fk in ['spec.cpu_cores', 'spec.memory_gb', 'spec.storage_gb']:
                print(f'Group-{num}: {fk} = {field.get("true_value")}')
                found = True

if not found:
    print("未使用这些字段")

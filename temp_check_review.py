import json
import os

review_dir = 'database/review'

# 允许的 invalid_reason 白名单
valid_reasons = {'accessory', 'ad', 'electronic_parts', 'non_target', 'pawn', 'recycling', 'service', 'other'}

# 允许的 field_key 白名单
valid_fields = {
    'item.normalized_brand', 'item.normalized_model_family', 'item.normalized_model',
    'item.normalized_chip', 'item.normalized_memory_gb', 'item.normalized_storage_gb',
    'spec.brand', 'spec.product_line', 'spec.model_family', 'spec.model_name',
    'spec.generation', 'spec.case_size_mm', 'spec.is_solar', 'spec.display_type',
    'spec.screen_size_in', 'spec.chip_family', 'spec.cpu_model', 'spec.cpu_cores',
    'spec.gpu_cores', 'spec.memory_gb', 'spec.storage_gb'
}

print('Review 文件统计：')
print('=' * 80)

total_valid = 0
total_invalid = 0
total_items = 0
invalid_reasons_used = set()
fields_used = set()
errors = []

for i in range(1, 21):
    num = f'{i:02d}'
    r_file = f'{review_dir}/group-{num}.review.json'

    try:
        with open(r_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        valid_count = sum(1 for item in data if item.get('review_status') == 'valid')
        invalid_count = sum(1 for item in data if item.get('review_status') == 'invalid')
        total_valid += valid_count
        total_invalid += invalid_count
        total_items += len(data)

        for item in data:
            # 收集 invalid_reason
            reason = item.get('invalid_reason')
            if reason:
                invalid_reasons_used.add(reason)
                if reason not in valid_reasons:
                    errors.append(f'Group-{num}: 无效的 invalid_reason: {reason}')

            # 收集 field_key
            for field in item.get('not_match_field', []):
                fk = field.get('field_key')
                if fk:
                    fields_used.add(fk)
                    if fk not in valid_fields:
                        errors.append(f'Group-{num}: 无效的 field_key: {fk}')

            # 检查 invalid 时 not_match_field 是否为空
            if item.get('review_status') == 'invalid':
                if item.get('not_match_field'):
                    errors.append(f"Group-{num}: Item {item.get('item_id')} 为 invalid 但 not_match_field 非空")

        print(f'Group-{num}: 总记录={len(data)}, valid={valid_count}, invalid={invalid_count}')

    except Exception as e:
        errors.append(f'Group-{num}: 读取错误: {e}')
        print(f'Group-{num}: Error - {e}')

print('=' * 80)
print(f'总计: 总记录={total_items}, valid={total_valid}, invalid={total_invalid}')
print('')
print('使用的 invalid_reason:', sorted(invalid_reasons_used))
print('')
print('使用的 field_key:', sorted(fields_used))
print('')
if errors:
    print('发现的问题:')
    for e in errors[:20]:
        print(f'  - {e}')
else:
    print('未发现格式问题')

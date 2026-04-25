import type { OnboardingAttributeOption, OnboardingAttributeObservation } from '../api/onboardingSchemas';

const ATTRIBUTE_CODE_RULES = [
  { pattern: /(品牌|brand)/i, code: 'brand_name' },
  { pattern: /(产品线|系列|lineage)/i, code: 'product_line' },
  { pattern: /(型号|model)/i, code: 'model_name' },
  { pattern: /(代际|代数|generation)/i, code: 'generation' },
  { pattern: /(芯片|处理器系列|chip)/i, code: 'chip_family' },
  { pattern: /(cpu)/i, code: 'cpu_model' },
  { pattern: /(gpu型号|显卡型号|gpu model)/i, code: 'gpu_model' },
  { pattern: /(gpu厂商|显卡厂商|gpu vendor)/i, code: 'gpu_vendor' },
  { pattern: /(显存|vram)/i, code: 'vram_gb' },
  { pattern: /(内存|memory|ram)/i, code: 'memory_gb' },
  { pattern: /(存储|硬盘|容量|storage|ssd)/i, code: 'storage_gb' },
  { pattern: /(屏幕|尺寸|screen)/i, code: 'screen_size_in' },
  { pattern: /(表径|case size)/i, code: 'case_size_mm' },
  { pattern: /(显示|屏幕类型|display)/i, code: 'display_type' },
  { pattern: /(光圈|aperture)/i, code: 'max_aperture' },
  { pattern: /(焦段|焦距|focal)/i, code: 'focal_length_range' },
  { pattern: /(卡口|mount)/i, code: 'mount_system' },
  { pattern: /(镜头系列|lens series)/i, code: 'lens_series' },
  { pattern: /(机身系列|camera series)/i, code: 'camera_series' },
  { pattern: /(传感器|sensor)/i, code: 'sensor_format' },
  { pattern: /(手机系列|phone series)/i, code: 'phone_series' },
  { pattern: /(颜色|color|colour)/i, code: 'device_color' },
  { pattern: /(乐器类型|乐器品类|instrument)/i, code: 'instrument_family' },
  { pattern: /(solar|太阳能)/i, code: 'is_solar' },
  { pattern: /(edition|版本标签|标签)/i, code: 'edition_tags' },
];

const OPTION_CODE_RULES = [
  { pattern: /(黑色|曜黑|black)/i, code: 'black' },
  { pattern: /(白色|white)/i, code: 'white' },
  { pattern: /(银色|silver)/i, code: 'silver' },
  { pattern: /(金色|gold)/i, code: 'gold' },
  { pattern: /(蓝色|blue)/i, code: 'blue' },
  { pattern: /(绿色|green)/i, code: 'green' },
  { pattern: /(紫色|purple)/i, code: 'purple' },
  { pattern: /(粉色|pink)/i, code: 'pink' },
  { pattern: /(红色|red)/i, code: 'red' },
  { pattern: /(全画幅|full frame)/i, code: 'full_frame' },
  { pattern: /(aps-c|半画幅|apsc)/i, code: 'aps_c' },
];

function slugifyCodeCandidate(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replaceAll(/[^a-z0-9]+/g, '_')
    .replaceAll(/^_+|_+$/g, '')
    .slice(0, 48);
}

export function suggestAttributeCode(name: string, fallback: string = 'custom_attr'): string {
  const label = name.trim();
  if (!label) {
    return fallback;
  }
  const matchedRule = ATTRIBUTE_CODE_RULES.find((entry) => entry.pattern.test(label));
  if (matchedRule) {
    return matchedRule.code;
  }
  const slug = slugifyCodeCandidate(label);
  if (slug) {
    return slug;
  }
  return fallback;
}

export function suggestOptionCode(name: string, index: number): string {
  const label = name.trim();
  if (!label) {
    return `option_${index}`;
  }
  const matchedRule = OPTION_CODE_RULES.find((entry) => entry.pattern.test(label));
  if (matchedRule) {
    return matchedRule.code;
  }
  const slug = slugifyCodeCandidate(label);
  if (slug) {
    return slug;
  }
  return `option_${index}`;
}

export function formatOptionLines(options: OnboardingAttributeOption[]): string {
  return options
    .map((option, index) => {
      const optionName = (option.optionName || '').trim();
      if (!optionName) {
        return '';
      }
      const code = (option.optionCode || '').trim() || suggestOptionCode(optionName, index + 1);
      return `${code}|${optionName}`;
    })
    .filter(Boolean)
    .join('\n');
}

export function parseDraftOptionsText(text: string): OnboardingAttributeOption[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      const parts = line.split('|').map((entry) => entry.trim()).filter(Boolean);
      const optionName = parts.length > 1 ? parts[1] : parts[0] || '';
      const optionCode = parts.length > 1 ? parts[0] : suggestOptionCode(optionName, index + 1);
      return {
        optionCode,
        optionName,
        sortNo: (index + 1) * 10,
        status: 'ACTIVE',
      };
    })
    .filter((entry) => entry.optionCode && entry.optionName);
}

export interface DraftAttributeRow {
  enabled: boolean;
  code: string;
  name: string;
  dataType: string;
  valueScope: string;
  unit: string | null;
  sortNo: number;
  isMulti: boolean;
  isRequired: boolean;
  isSale: boolean;
  isFilter: boolean;
  isSearch: boolean;
  isDisplay: boolean;
  optionsText: string;
  options: OnboardingAttributeOption[];
  sampleValues: unknown[];
  profileSuggested: boolean;
  suggestedCode: string;
  observedCount: number;
}

export function initializeDraftAttributeRows(
  analysis: { attributeObservations?: OnboardingAttributeObservation[] } | null | undefined,
  catalogAttributes: Record<string, unknown>[] = [],
  templateItems: Record<string, unknown>[] = [],
): DraftAttributeRow[] {
  const observations = analysis?.attributeObservations || [];
  
  return observations
    .filter((entry) => entry?.visible !== false)
    .map((observation) => {
      const code = String(observation.attributeCode || '');
      const catalogAttr = catalogAttributes.find(attr => attr.code === code);
      const templateItem = templateItems.find(item => item.attributeCode === code);
      
      const options = (catalogAttr?.options as OnboardingAttributeOption[] || []).length
        ? (catalogAttr!.options as OnboardingAttributeOption[])
        : (observation.optionSuggestions || []);
      
      return {
        enabled: Boolean(observation.selected),
        code: code,
        name: observation.attributeName || (catalogAttr?.name as string) || code,
        dataType: observation.dataType || (catalogAttr?.dataType as string) || 'TEXT',
        valueScope: observation.valueScope || (catalogAttr?.valueScope as string) || 'SPU',
        unit: observation.unit || (catalogAttr?.unit as string) || null,
        sortNo: Number(templateItem?.sortNo || observation.sortNo || 0),
        isMulti: Boolean(observation.isMulti ?? (catalogAttr?.isMulti as boolean)),
        isRequired: Boolean(templateItem?.isRequired),
        isSale: Boolean(templateItem?.isSale),
        isFilter: Boolean(templateItem?.isFilter),
        isSearch: templateItem?.isSearch === undefined
          ? (code === 'brand_name' || code === 'model_name')
          : Boolean(templateItem.isSearch),
        isDisplay: templateItem?.isDisplay === undefined ? true : Boolean(templateItem.isDisplay),
        optionsText: formatOptionLines(options),
        options: options,
        sampleValues: observation.sampleValues || [],
        profileSuggested: Boolean(observation.profileSuggested),
        suggestedCode: String(observation.suggestedCode || code || 'custom_attr'),
        observedCount: Number(observation.observedCount || 0),
      };
    })
    .sort((left, right) => left.sortNo - right.sortNo || left.code.localeCompare(right.code, 'zh-CN'));
}

"""Ядро: валидация + исправление XML по XSD. Зависимость: pip install lxml"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable, List, Dict, Tuple
from lxml import etree


# ═══════════════════════════════════════════════════════════
#  МОДЕЛИ ДАННЫХ
# ═══════════════════════════════════════════════════════════

@dataclass
class ValidationError:
    """Ошибка валидации."""
    level: str
    line: int
    column: int
    message: str

    def __str__(self) -> str:
        return f"[{self.level}] Стр. {self.line}, кол. {self.column}: {self.message}"


@dataclass
class FixResult:
    """Результат применённого исправления."""
    element_path: str
    action: str
    details: str


@dataclass
class ValidationResult:
    """Результат валидации XML-файла."""
    file_path: Path
    is_valid: bool
    is_wellformed: bool = True
    errors: List[ValidationError] = field(default_factory=list)
    root_element: Optional[str] = None
    elements_checked: int = 0
    elements_valid: int = 0
    fixes_applied: List[FixResult] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        """Возвращает количество ошибок."""
        return len(self.errors)


_LEVEL_MAP = {0: "WARNING", 1: "ERROR", 2: "FATAL"}
XS_NS = "http://www.w3.org/2001/XMLSchema"

_DEFAULT_VALUES = {
    "xs:string": "",
    "xs:integer": "0",
    "xs:decimal": "0.00",
    "xs:date": "2000-01-01",
}


# ═══════════════════════════════════════════════════════════
#  ЗАГРУЗКА СХЕМЫ
# ═══════════════════════════════════════════════════════════

def load_xsd_schema(xsd_path: Path) -> etree.XMLSchema:
    """Загружает XSD-схему из файла и возвращает объект XMLSchema."""
    xsd_path = Path(xsd_path).resolve()
    if not xsd_path.exists():
        raise FileNotFoundError(f"XSD не найден: {xsd_path}")
    raw = xsd_path.read_bytes()
    parser = etree.XMLParser()
    xsd_doc = etree.fromstring(raw, parser, base_url=str(xsd_path))
    return etree.XMLSchema(xsd_doc)


def get_schema_root_elements(xsd_path: Path) -> List[str]:
    """Возвращает список имён корневых элементов, объявленных в XSD."""
    raw = Path(xsd_path).read_bytes()
    xsd_doc = etree.XML(raw)
    elements = xsd_doc.findall(f"{{{XS_NS}}}element")
    return [el.get("name") for el in elements if el.get("name")]


# ═══════════════════════════════════════════════════════════
#  ПАРСИНГ СТРУКТУРЫ XSD
# ═══════════════════════════════════════════════════════════

@dataclass
class XsdElementInfo:
    """Информация об элементе в XSD."""
    name: str
    min_occurs: int
    max_occurs: int
    xs_type: Optional[str]
    is_simple: bool


class XsdStructure:
    """
    Распарсенная структура XSD.
    Разрешает типы дочерних элементов в контексте родителя, а не глобально.
    """

    def __init__(self, xsd_path: Path):
        self._xsd_path = Path(xsd_path)
        raw = self._xsd_path.read_bytes()
        self._xsd_doc = etree.XML(raw)

        # { имя_типа: [XsdElementInfo, ...] }
        self._type_sequences: Dict[str, List[XsdElementInfo]] = {}

        # { имя_типа: { имя_дочернего_элемента: имя_типа_дочернего } }
        self._type_child_map: Dict[str, Dict[str, str]] = {}

        # { имя_корневого_элемента: имя_типа }
        self._root_element_types: Dict[str, str] = {}

        self._parse()

    def _parse(self):
        # 1. Именованные complexType
        for ct in self._xsd_doc.iter(f"{{{XS_NS}}}complexType"):
            name = ct.get("name")
            if name:
                self._parse_complex_type(name, ct)

        # 2. Корневые элементы (могут иметь inline complexType или атрибут type)
        for elem in self._xsd_doc.findall(f"{{{XS_NS}}}element"):
            elem_name = elem.get("name")
            if not elem_name:
                continue

            etype = elem.get("type")
            if etype:
                self._root_element_types[elem_name] = etype
            else:
                inline_ct = elem.find(f"{{{XS_NS}}}complexType")
                if inline_ct is not None:
                    synthetic_name = f"__root__{elem_name}"
                    self._root_element_types[elem_name] = synthetic_name
                    self._parse_complex_type(synthetic_name, inline_ct)

    def _parse_complex_type(self, type_name: str, ct_element: etree._Element):
        """Парсит complexType и извлекает информацию о дочерних элементах."""
        elements = []
        child_map = {}

        for seq in ct_element.iter(f"{{{XS_NS}}}sequence"):
            for elem in seq.findall(f"{{{XS_NS}}}element"):
                name = elem.get("name")
                if not name:
                    continue

                min_occ = int(elem.get("minOccurs", "1"))
                max_occ_str = elem.get("maxOccurs", "1")
                max_occ = -1 if max_occ_str == "unbounded" else int(max_occ_str)

                xs_type = elem.get("type")

                if xs_type is None:
                    inline_st = elem.find(f"{{{XS_NS}}}simpleType")
                    inline_ct = elem.find(f"{{{XS_NS}}}complexType")
                    if inline_st is not None:
                        xs_type = "xs:string"
                    elif inline_ct is not None:
                        xs_type = None

                is_simple = xs_type is not None and xs_type.startswith("xs:")

                elements.append(XsdElementInfo(
                    name=name,
                    min_occurs=min_occ,
                    max_occurs=max_occ,
                    xs_type=xs_type,
                    is_simple=is_simple,
                ))

                # Отслеживаем тип дочернего элемента для рекурсии
                if xs_type and not xs_type.startswith("xs:"):
                    child_map[name] = xs_type

        self._type_sequences[type_name] = elements
        self._type_child_map[type_name] = child_map

    def get_root_type(self, root_tag: str) -> Optional[str]:
        """Возвращает имя типа для корневого элемента по его тегу."""
        return self._root_element_types.get(root_tag)

    def get_sequence(self, type_name: str) -> List[XsdElementInfo]:
        """Возвращает последовательность элементов для указанного типа."""
        return self._type_sequences.get(type_name, [])

    def get_child_type(self, parent_type: str, child_tag: str) -> Optional[str]:
        """
        По имени complexType родителя и тегу дочернего элемента
        возвращает имя complexType дочернего элемента (или None, если тип простой/неизвестен).
        """
        child_map = self._type_child_map.get(parent_type, {})
        return child_map.get(child_tag)

    def get_expected_order(self, parent_tag: str) -> List[str]:
        """Возвращает ожидаемый порядок дочерних элементов для тега родителя (поиск на корневом уровне)."""
        # Сначала пробуем найти тип корневого элемента
        type_name = self._root_element_types.get(parent_tag)
        if not type_name:
            # Пробуем как имя типа напрямую
            for tn, seq in self._type_sequences.items():
                for info in seq:
                    if info.name == parent_tag and info.xs_type:
                        type_name = info.xs_type
                        break
                if type_name:
                    break

        # Резервный вариант: поиск во всех типах этого тега как дочернего
        if not type_name:
            for tn, child_map in self._type_child_map.items():
                if parent_tag in child_map:
                    type_name = child_map[parent_tag]
                    break

        if not type_name:
            return []

        return [info.name for info in self._type_sequences.get(type_name, [])]


# ═══════════════════════════════════════════════════════════
#  ИСПРАВЛЕНИЕ ОТСУТСТВУЮЩИХ ЭЛЕМЕНТОВ — РЕКУРСИЯ С УЧЁТОМ КОНТЕКСТА
# ═══════════════════════════════════════════════════════════

def fix_missing_elements(
    xml_element: etree._Element,
    xsd_path: Path,
    fixes_log: List[FixResult],
    parent_path: str = "",
):
    """
    Рекурсивно добавляет отсутствующие обязательные элементы в XML
    согласно структуре XSD, с учётом контекста типов.
    """
    structure = XsdStructure(xsd_path)
    tag = etree.QName(xml_element.tag).localname
    current_path = f"{parent_path}/{tag}" if parent_path else tag

    # Определяем тип корневого элемента
    root_type = structure.get_root_type(tag)
    if root_type:
        _fix_with_context(xml_element, root_type, structure, fixes_log, current_path)


def _fix_with_context(
    xml_element: etree._Element,
    type_name: str,
    structure: XsdStructure,
    fixes_log: List[FixResult],
    current_path: str,
):
    """
    Исправляет элемент, зная его точный complexType из контекста родителя.
    Это позволяет избежать коллизий «тег-тип» на глобальном уровне.
    """
    expected = structure.get_sequence(type_name)
    if not expected:
        return

    # Шаг 1: Переупорядочивание + вставка отсутствующих обязательных
    _reorder_and_insert(xml_element, expected, fixes_log, current_path)

    # Шаг 2: Рекурсия по дочерним элементам с разрешением типов в контексте
    for child in list(xml_element):
        child_tag = etree.QName(child.tag).localname
        child_path = f"{current_path}/{child_tag}"

        # Спрашиваем: какой тип имеет ЭТОТ дочерний элемент в контексте типа родителя?
        child_type = structure.get_child_type(type_name, child_tag)
        if child_type:
            _fix_with_context(child, child_type, structure, fixes_log, child_path)


def _reorder_and_insert(
    xml_element: etree._Element,
    expected: List[XsdElementInfo],
    fixes_log: List[FixResult],
    current_path: str,
):
    """Переупорядочивает дочерние элементы согласно XSD и добавляет отсутствующие обязательные."""
    # Собираем существующие дочерние элементы, сгруппированные по тегам
    existing_by_tag: Dict[str, List[etree._Element]] = {}
    for child in xml_element:
        child_tag = etree.QName(child.tag).localname
        if child_tag not in existing_by_tag:
            existing_by_tag[child_tag] = []
        existing_by_tag[child_tag].append(child)

    # Удаляем все дочерние элементы
    for child in list(xml_element):
        xml_element.remove(child)

    # Восстанавливаем в правильном порядке
    used_tags = set()

    for info in expected:
        tag_name = info.name
        if tag_name in existing_by_tag:
            for child in existing_by_tag[tag_name]:
                xml_element.append(child)
            used_tags.add(tag_name)
        elif info.min_occurs > 0:
            new_elem = etree.SubElement(xml_element, tag_name)
            if info.is_simple and info.xs_type:
                new_elem.text = _DEFAULT_VALUES.get(info.xs_type, "")
            else:
                new_elem.text = ""
            fixes_log.append(FixResult(
                element_path=f"{current_path}/{tag_name}",
                action="added",
                details=(
                    f"Добавлен отсутствующий обязательный <{tag_name}> "
                    f"(тип={info.xs_type or 'complex'}, "
                    f"значение по умолчанию='{new_elem.text}')"
                ),
            ))
            used_tags.add(tag_name)

    # Добавляем «лишние» элементы, не описанные в схеме
    for tag_name, children in existing_by_tag.items():
        if tag_name not in used_tags:
            for child in children:
                xml_element.append(child)


# ═══════════════════════════════════════════════════════════
#  ЗАМЕНА ЗНАЧЕНИЙ ЭЛЕМЕНТОВ
# ═══════════════════════════════════════════════════════════

def replace_element_value(
    xml_path: Path,
    element_name: str,
    new_value: str,
    encoding: str = "windows-1251",
) -> Tuple[int, Path]:
    """Заменяет текст во всех элементах с указанным именем. Возвращает количество замен и путь к файлу."""
    raw = xml_path.read_bytes()
    xml_doc = etree.XML(raw)
    count = 0
    for elem in xml_doc.iter(element_name):
        elem.text = new_value
        count += 1
    _save_xml(xml_doc, xml_path, encoding)
    return count, xml_path

def replace_lpu1_for_specific_usl(
    xml_path: Path,
    target_codes: List[str],
    new_lpu1: str,
    encoding: str = "windows-1251"
) -> Tuple[int, Path]:
    """
    Заменяет значение LPU_1 внутри блоков USL, где CODE_USL совпадает с target_codes.
    Возвращает количество замен и путь к файлу.
    """
    raw = xml_path.read_bytes()
    xml_doc = etree.XML(raw)
    count = 0
    
    # Ищем все блоки USL
    for usl in xml_doc.iter("USL"):
        code_elem = usl.find("CODE_USL")
        if code_elem is not None and code_elem.text in target_codes:
            # Если код подходит, ищем LPU_1 внутри этого USL
            lpu1_elem = usl.find("LPU_1")
            if lpu1_elem is not None:
                lpu1_elem.text = new_lpu1
                count += 1
                
    if count > 0:
        _save_xml(xml_doc, xml_path, encoding)
        
    return count, xml_path


# ═══════════════════════════════════════════════════════════
#  UPSERT ЭЛЕМЕНТА (ВСТАВИТЬ ИЛИ ЗАМЕНИТЬ)
# ═══════════════════════════════════════════════════════════

def upsert_element_value(
    xml_path: Path,
    parent_tag: str,
    element_name: str,
    new_value: str,
    xsd_path: Optional[Path] = None,
    encoding: str = "windows-1251",
) -> Tuple[int, int, Path]:
    """
    Вставляет новый элемент или заменяет существующий внутри родителя.
    Если указана XSD-схема, пытается вставить элемент в правильную позицию.
    Возвращает (количество замен, количество созданных, путь к файлу).
    """
    raw = xml_path.read_bytes()
    xml_doc = etree.XML(raw)

    expected_order = []
    if xsd_path:
        structure = XsdStructure(xsd_path)
        expected_order = structure.get_expected_order(parent_tag)

    replaced = 0
    created = 0

    for parent in xml_doc.iter(parent_tag):
        existing = parent.find(element_name)
        if existing is not None:
            existing.text = new_value
            replaced += 1
        else:
            new_elem = etree.Element(element_name)
            new_elem.text = new_value
            if expected_order and element_name in expected_order:
                _insert_at_correct_position(parent, new_elem, expected_order)
            else:
                parent.append(new_elem)
            created += 1

    _save_xml(xml_doc, xml_path, encoding)
    return replaced, created, xml_path


def _insert_at_correct_position(
    parent: etree._Element,
    new_element: etree._Element,
    expected_order: List[str],
):
    """Вставляет новый элемент в позицию, соответствующую порядку из XSD."""
    target_name = etree.QName(new_element.tag).localname
    if target_name not in expected_order:
        parent.append(new_element)
        return

    target_idx = expected_order.index(target_name)
    after_names = set(expected_order[target_idx + 1:])

    for i, child in enumerate(parent):
        child_tag = etree.QName(child.tag).localname
        if child_tag in after_names:
            parent.insert(i, new_element)
            return

    parent.append(new_element)


# ═══════════════════════════════════════════════════════════
#  ПОЛНЫЙ ЦИКЛ: ИСПРАВЛЕНИЕ + СОХРАНЕНИЕ
# ═══════════════════════════════════════════════════════════

def fix_and_save_xml(
    xml_path: Path,
    xsd_path: Path,
    schema: etree.XMLSchema,
    output_path: Optional[Path] = None,
    encoding: str = "windows-1251",
) -> Tuple[ValidationResult, List[FixResult]]:
    """
    Исправляет XML-файл согласно XSD, сохраняет результат и возвращает отчёт о валидации.
    Если output_path не указан, создаёт файл с суффиксом _fixed.
    """
    xml_path = Path(xml_path)
    if output_path is None:
        stem = xml_path.stem
        output_path = xml_path.parent / f"{stem}_fixed{xml_path.suffix}"

    raw = xml_path.read_bytes()
    try:
        xml_doc = etree.XML(raw)
    except etree.XMLSyntaxError as e:
        return ValidationResult(
            file_path=xml_path, is_valid=False, is_wellformed=False,
            errors=[ValidationError("FATAL", 0, 0, f"Синтаксис XML: {e}")],
        ), []

    root_name = etree.QName(xml_doc.tag).localname
    fixes_log: List[FixResult] = []

    # Исправляем начиная с корня — рекурсия обрабатывает всё
    fix_missing_elements(xml_doc, xsd_path, fixes_log)

    # Сохраняем
    _save_xml(xml_doc, output_path, encoding)

    # Валидируем
    is_valid = schema.validate(xml_doc)
    errors = []
    if not is_valid:
        for err in schema.error_log:
            level = _LEVEL_MAP.get(err.level, "UNKNOWN")
            errors.append(ValidationError(level, err.line, err.column, err.message))

    result = ValidationResult(
        file_path=output_path,
        is_valid=is_valid,
        is_wellformed=True,
        errors=errors,
        root_element=root_name,
        fixes_applied=fixes_log,
    )

    return result, fixes_log


def _save_xml(
    xml_doc: etree._Element,
    path: Path,
    encoding: str = "windows-1251",
):
    """Сохраняет XML-документ в файл с указанной кодировкой."""
    tree = etree.ElementTree(xml_doc)
    with open(path, "wb") as f:
        tree.write(f, encoding=encoding, xml_declaration=True, pretty_print=True)


# ═══════════════════════════════════════════════════════════
#  ВАЛИДАЦИЯ
# ═══════════════════════════════════════════════════════════

def _collect_errors(schema: etree.XMLSchema) -> List[ValidationError]:
    """Собирает ошибки из error_log схемы в список ValidationError."""
    errors = []
    for err in schema.error_log:
        level = _LEVEL_MAP.get(err.level, "UNKNOWN")
        errors.append(ValidationError(level, err.line, err.column, err.message))
    return errors


def _find_elements_recursive(
    root: etree._Element, tag: str,
) -> List[etree._Element]:
    """Рекурсивно ищет элементы с указанным тегом, начиная с корня."""
    direct = [ch for ch in root if etree.QName(ch.tag).localname == tag]
    if direct:
        return direct
    found = []
    for ch in root:
        found.extend(_find_elements_recursive(ch, tag))
    return found


def validate_xml(
    xml_path: Path,
    schema: etree.XMLSchema,
    expected_root: Optional[str] = None,
    validate_children: bool = False,
    child_tag: Optional[str] = None,
) -> ValidationResult:
    """
    Валидирует XML-файл против XSD-схемы.
    Поддерживает проверку корня и опциональную валидацию дочерних элементов.
    """
    xml_path = Path(xml_path)

    if not xml_path.exists():
        return ValidationResult(
            file_path=xml_path, is_valid=False, is_wellformed=False,
            errors=[ValidationError("FATAL", 0, 0, f"Не найден: {xml_path}")],
        )

    try:
        raw = xml_path.read_bytes()
        xml_doc = etree.XML(raw)
    except etree.XMLSyntaxError as e:
        return ValidationResult(
            file_path=xml_path, is_valid=False, is_wellformed=False,
            errors=[ValidationError("FATAL", 0, 0, f"Синтаксис XML: {e}")],
        )

    root_name = etree.QName(xml_doc.tag).localname
    is_valid = schema.validate(xml_doc)

    if is_valid:
        if expected_root and root_name != expected_root:
            return ValidationResult(
                file_path=xml_path, is_valid=False, is_wellformed=True,
                root_element=root_name,
                errors=[ValidationError(
                    "ERROR", 1, 0,
                    f"Корень '{root_name}' != ожидаемый '{expected_root}'"
                )],
            )
        return ValidationResult(
            file_path=xml_path, is_valid=True, is_wellformed=True,
            root_element=root_name,
        )

    root_errors = _collect_errors(schema)
    is_root_unknown = any(
        "No matching global declaration" in e.message for e in root_errors
    )

    if is_root_unknown and validate_children and child_tag:
        return _validate_children_elements(
            xml_path, xml_doc, schema, root_name, child_tag,
        )

    return ValidationResult(
        file_path=xml_path, is_valid=False, is_wellformed=True,
        errors=root_errors, root_element=root_name,
    )


def _validate_children_elements(
    xml_path, xml_doc, schema, root_name, child_tag,
) -> ValidationResult:
    """
    Валидирует дочерние элементы с указанным тегом,
    если корневой элемент не описан в схеме.
    """
    children = _find_elements_recursive(xml_doc, child_tag)

    if not children:
        return ValidationResult(
            file_path=xml_path, is_valid=False, is_wellformed=True,
            root_element=root_name,
            errors=[ValidationError(
                "ERROR", 1, 0,
                f"Корень '{root_name}' не описан в схеме. "
                f"<{child_tag}> не найден."
            )],
        )

    all_errors: List[ValidationError] = []
    checked = 0
    valid_count = 0

    for child in children:
        checked += 1
        n_zap_el = child.find("N_ZAP")
        n_zap = n_zap_el.text if n_zap_el is not None else str(checked)

        child_valid = schema.validate(child)
        if child_valid:
            valid_count += 1
        else:
            all_errors.append(ValidationError(
                "INFO", child.sourceline or 0, 0,
                f"--- {child_tag} N_ZAP={n_zap} "
                f"(строка ~{child.sourceline or '?'}) ---"
            ))
            for err in schema.error_log:
                level = _LEVEL_MAP.get(err.level, "UNKNOWN")
                all_errors.append(
                    ValidationError(level, err.line, err.column, err.message)
                )

    is_all_valid = (valid_count == checked)
    summary = (
        f"Корень '{root_name}' не описан в схеме -> "
        f"проверено <{child_tag}>: "
        f"всего {checked}, валидных {valid_count}, "
        f"ошибок {checked - valid_count}"
    )
    all_errors.insert(0, ValidationError("INFO", 0, 0, summary))

    return ValidationResult(
        file_path=xml_path, is_valid=is_all_valid, is_wellformed=True,
        errors=all_errors, root_element=root_name,
        elements_checked=checked, elements_valid=valid_count,
    )


def validate_batch(
    xml_paths: List[Path],
    schema: etree.XMLSchema,
    expected_root: Optional[str] = None,
    validate_children: bool = False,
    child_tag: Optional[str] = None,
    on_progress: Optional[Callable] = None,
) -> List[ValidationResult]:
    """
    Пакетная валидация списка XML-файлов.
    on_progress(i, total) — опциональный колбэк для отслеживания прогресса.
    """
    results = []
    total = len(xml_paths)
    for i, p in enumerate(xml_paths, 1):
        results.append(validate_xml(
            p, schema, expected_root,
            validate_children=validate_children,
            child_tag=child_tag,
        ))
        if on_progress:
            on_progress(i, total)
    return results


def collect_xml_files(directory: Path) -> List[Path]:
    """Возвращает отсортированный список всех *.xml файлов в директории."""
    d = Path(directory)
    if not d.is_dir():
        raise NotADirectoryError(f"Не директория: {d}")
    return sorted(d.glob("*.xml"))


def get_records_with_for_pom(
    xml_path: Path,
    for_pom_value: str = "3",
) -> List[dict]:
    """
    Возвращает список записей, где FOR_POM == for_pom_value.
    Каждая запись: dict с полями для отображения и редактирования.
    """
    raw = xml_path.read_bytes()
    xml_doc = etree.XML(raw)
    records = []

    for zap in xml_doc.iter("ZAP"):
        n_zap_el = zap.find("N_ZAP")
        n_zap = n_zap_el.text if n_zap_el is not None else "?"

        z_sl = zap.find("Z_SL")
        if z_sl is None:
            continue

        for_pom_el = z_sl.find("FOR_POM")
        if for_pom_el is None or for_pom_el.text != for_pom_value:
            continue

        idcase_el  = z_sl.find("IDCASE")
        npr_mo_el  = z_sl.find("NPR_MO")
        npr_date_el = z_sl.find("NPR_DATE")
        npr_num_el  = z_sl.find("NPR_NUM")

        # Пациент
        pacient = zap.find("PACIENT")
        id_pac = ""
        if pacient is not None:
            id_pac_el = pacient.find("ID_PAC")
            if id_pac_el is not None:
                id_pac = id_pac_el.text or ""

        # N_HISTORY из первого SL внутри Z_SL
        nhistory = ""
        sl_el = z_sl.find("SL")
        if sl_el is not None:
            nhistory_el = sl_el.find("NHISTORY")
            if nhistory_el is not None:
                nhistory = nhistory_el.text or ""

        records.append({
            "file_path":  xml_path,
            "n_zap":      n_zap,
            "idcase":     idcase_el.text  if idcase_el  is not None else "",
            "id_pac":     id_pac,
            "nhistory":   nhistory,
            "npr_mo":     npr_mo_el.text  if npr_mo_el  is not None else "",
            "npr_date":   npr_date_el.text if npr_date_el is not None else "",
            "npr_num":    npr_num_el.text  if npr_num_el  is not None else "",
            "for_pom":    for_pom_el.text,
        })

    return records


def set_npr_num(
    xml_path: Path,
    idcase: str,
    npr_num_value: str,
    encoding: str = "windows-1251",
) -> bool:
    """
    Находит Z_SL по IDCASE и вставляет/обновляет NPR_NUM после NPR_DATE.
    Возвращает True, если нашёл и обновил.
    """
    raw = xml_path.read_bytes()
    xml_doc = etree.XML(raw)
    updated = False

    for z_sl in xml_doc.iter("Z_SL"):
        idcase_el = z_sl.find("IDCASE")
        if idcase_el is None or idcase_el.text != idcase:
            continue

        # Обновляем, если уже есть
        existing = z_sl.find("NPR_NUM")
        if existing is not None:
            existing.text = npr_num_value
            updated = True
            break

        # Вставляем после NPR_DATE
        children = list(z_sl)
        tags = [etree.QName(c.tag).localname for c in children]

        insert_after = -1
        for priority_tag in ("NPR_DATE", "NPR_MO", "LPU"):
            if priority_tag in tags:
                insert_after = tags.index(priority_tag)
                break

        new_elem = etree.Element("NPR_NUM")
        new_elem.text = npr_num_value

        if insert_after >= 0:
            z_sl.insert(insert_after + 1, new_elem)
        else:
            z_sl.append(new_elem)

        updated = True
        break

    if updated:
        _save_xml(xml_doc, xml_path, encoding)

    return updated
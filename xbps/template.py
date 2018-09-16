from typing import Optional, List
import regex as re


class TemplateParser:
    REGEX_WHITESPACE = re.compile(r"^[\s\n]+", re.M)
    REGEX_COMMENT = re.compile("^#[^\n]+")
    REGEX_KV = re.compile("^(?P<key>[A-Za-z0-9_\-]+)=(?P<value>[^\"][^\n]*|\"(?:[^\"]+)\")")
    REGEX_FUNC = re.compile("^(?P<name>[^\s]+)\s*\(\)\s*{\n.+?^}", re.M + re.S)

    TYPE_WS = 1
    TYPE_COMMENT = 2
    TYPE_KV = 4
    TYPE_FUNC = 8

    REGEX_STRING_ARG = re.compile("\$(?P<a>{)?(?P<key>[A-Za-z_]+)(?(a)})")

    def __init__(self):
        self.parts = []

    def consume(self, data: str) -> str:

        while len(data) > 0:
            match = self.REGEX_WHITESPACE.match(data)

            if match:
                self.parts.append((self.TYPE_WS, data[:match.end()]))
                data = data[match.end():]
                continue

            match = self.REGEX_COMMENT.match(data)

            if match:
                self.parts.append((self.TYPE_COMMENT, data[:match.end()]))
                data = data[match.end():]
                continue

            match = self.REGEX_KV.match(data)

            if match:
                val = match.group('value')
                quoted = False

                if val[0] == '"':
                    quoted = True
                    val = val[1:-1]

                self.parts.append((self.TYPE_KV, match.group('key'), val, quoted))
                data = data[match.end():]
                continue

            match = self.REGEX_FUNC.match(data)

            if match:
                self.parts.append((self.TYPE_FUNC, data[:match.end()], match.group('name')))
                data = data[match.end():]
                continue

            break

        return data

    def write(self) -> str:
        output = ""

        for part in self.parts:
            if part[0] != self.TYPE_KV:
                output += part[1]
                continue

            output += part[1] + '='

            if not part[3]:
                output += part[2]
            else:
                output += '"' + part[2] + '"'

        return output

    def get(self, key, default: Optional[str] = None) -> Optional[str]:
        for part in [part for part in self.parts if part[0] == self.TYPE_KV]:
            if part[1] == key:
                return part[2]

        return default

    def set(self, key, value: str, quoted: Optional[bool] = None) -> bool:
        for idx, part in enumerate(self.parts):
            if part[0] == self.TYPE_KV and part[1] == key:
                self.parts[idx] = (part[0], part[1], value, quoted if quoted is not None else part[3])
                return True

        return False

    def insert_after(self, items: List, after: str) -> bool:
        items = list(items)
        found = False
        idx = None

        for idx, part in enumerate(self.parts):
            if part[0] == self.TYPE_KV and part[1] == after:
                found = True
                break

        if not found:
            return False

        self.parts = self.parts[:idx+1] + items + self.parts[idx+1:]

    def get_expanded(self, key: str, default: Optional[str] = None, visited: List[str] = None) -> Optional[str]:
        if visited is None:
            visited = [key]
        else:
            if key in visited:
                return default

            visited.append(key)

        source = self.get(key)

        if source is None:
            return default

        return re.sub(self.REGEX_STRING_ARG, lambda x: self.get_expanded(x.group('key'), "", visited), source)

    def get_func(self, key: str):
        for part in self.parts:
            if part[0] == self.TYPE_FUNC and part[2] == key:
                return part

        return None

    def set_func(self, key: str, body: str) -> bool:
        for idx, part in enumerate(self.parts):
            if part[0] == self.TYPE_FUNC and part[2] == key:
                self.parts[idx] = (part[0], body, part[2])
                return True

        return False

from typing import List, TypeVar, Tuple
import sys
import argparse
import jsbeautifier


class CaseBody(object):
    def __init__(self, text: str):
        self.text = text

    def __add__(self, other):
        return CaseBody(self.text + "\n" + other.text)


class Character():
    def __init__(self, name):
        if name == "Player":
            self.name = 'global.name'
        else:
            self.name = name


player = Character("global.name")


def uprint(*objects, sep=' ', end='\n', file=sys.stdout):
    enc = file.encoding
    if enc == 'UTF-8':
        print(*objects, sep=sep, end=end, file=file)
    else:
        f = lambda obj: str(obj).encode(enc, errors='backslashreplace').decode(enc)
        print(*map(f, objects), sep=sep, end=end, file=file)


def list_to_string(list_of_strings: List[str]) -> str:
    """Returns one string, where each item in the list
    is separated by a line and a tab"""
    nonempty = [s for s in list_of_strings if s.strip() != ""]
    return "\n\t".join(nonempty)


def flatten(l):
    """Sometimes we have lists of lists of X, and want
    lists of X instead"""
    if l == []:
        return l
    elif isinstance(l[0], list):
        return flatten(l[0]) + flatten(l[1:])
    else:
        return [l[0]] + flatten(l[1:])


class Parseable(object):
    """Abstract class representing a code concept, such as a Comment or Choice. These can then be turned into
    gamemaker code using the to_case_bodies method"""

    def __init__(self):
        raise NotImplementedError

    def to_case_bodies(self) -> List[CaseBody]:
        raise NotImplementedError


class Comment(Parseable):
    def __init__(self, line):
        assert line[0] == '(' and line[-1] == ')'
        self.clean_line = line[1:-1]

    def to_case_bodies(self) -> List[CaseBody]:
        return [CaseBody("//{clean_line};\n step += 1;".format(clean_line=self.clean_line))]


class SpecificAction(Parseable):
    def __init__(self, line):
        """Make sure that the text passed in actually starts and ends with braces"""
        assert line[0] == '{' and line[-1] == '}'
        self.clean_line = line[1:-1]

    def to_case_bodies(self) -> List[CaseBody]:
        """Leave one case with a comment, plus two empty cases to code manually."""
        case_containing_comment = "//TODO: {clean_line};\n".format(clean_line=self.clean_line)
        blank_case_1 = "//This case intentionally left blank;"
        blank_case_2 = "//This case intentionally left blank 2;"

        return [CaseBody(c) for c in [case_containing_comment, blank_case_1, blank_case_2]]


class Screen(Parseable):
    """Represents dialogue or the player thinking"""

    def __init__(self, character, text_style, lines_of_text: List[str]):
        self.character = character
        self.text_style = text_style
        self.lines_of_text = lines_of_text

        assert len(
            lines_of_text) < 5, "Text for dialogue or player thought is over maximum limit of 4 lines of 85 characters: {lines_of_text}".format(
            lines_of_text=lines_of_text)

    def to_case_bodies(self) -> List[CaseBody]:
        if self.character.name == player.name:
            announcer = '"You"'
        else:
            announcer = '"{name}"'.format(name=self.character.name)

        if self.text_style == "Thinking":
            announce = ""
        else:
            announce = "announce({announcer});".format(announcer=announcer)

        space_between_lines = 40
        gml_code_body = []
        for (index, line) in enumerate(self.lines_of_text):
            code = 'draw_text(x, y + {space}, "{line}");'.format(space=space_between_lines * index, line=line)
            gml_code_body += code

        return [CaseBody(list_to_string([announce, "".join(gml_code_body)]))]

    @staticmethod
    def split_text_into_multiple_lines(line: str, max_text_row_length: int = 85) -> List[str]:
        """Gamemaker lines of text can only be 85 characters long, or the text will go offscreen. This function splits
        those lines so that each new line contains fewer than 85 characters, and doesn't split any words apart."""
        if len(line) <= max_text_row_length:
            return [line]
        else:
            truncated_line = line[:max_text_row_length]
            last_space_index = truncated_line.rfind(" ")
            text_before_last_space = truncated_line[:last_space_index]
            text_after_last_space = line[last_space_index + 1:]
            return [text_before_last_space] + Screen.split_text_into_multiple_lines(text_after_last_space,
                                                                                    max_text_row_length)


class IfElse(Parseable):
    """A recursive Parseable representing an if-else branch. Each side of the branch has another parseable"""

    def __init__(self, if_parseables: List[Parseable], else_parseables: List[Parseable], condition_string: str):
        self.if_parseables = if_parseables
        self.else_parseables = else_parseables
        self.condition_string = condition_string.replace("\"+'\"", "\"").replace("\"'+\"", "\"")

    def to_case_bodies(self) -> List[CaseBody]:
        if_case_bodies = flatten([p.to_case_bodies() for p in self.if_parseables])
        else_case_bodies = flatten([p.to_case_bodies() for p in self.else_parseables])
        (augmented_if, augmented_else) = IfElse.fill_empty_cases(if_case_bodies, else_case_bodies)
        debug_print_variable(augmented_if, "augmented_if")
        debug_print_variable(augmented_else, "augmented_else")

        if_header = self.condition_string
        else_header = "else"
        wrapped_if = [CaseBody("\n".join([if_header, "{", body.text, "}"])) for body in augmented_if]
        wrapped_else = [CaseBody("\n".join([else_header, "{", body.text, "}"])) for body in augmented_else]
        pairs = zip(wrapped_if, wrapped_else)
        return [pair[0] + pair[1] for pair in pairs]

    @staticmethod
    def fill_empty_cases(left: List[CaseBody], right: List[CaseBody]) -> Tuple[List[CaseBody], List[CaseBody]]:
        if len(left) == len(right):
            return (left, right)
        elif len(left) < len(right):
            extra_steps = [CaseBody("step += 1;")] * (len(right) - len(left))
            return (left + extra_steps, right)
        elif len(right) < len(left):
            extra_steps = [CaseBody("step += 1;")] * (len(left) - len(right))
            return (left, right + extra_steps)


class Option(object):
    """Represents one of up to 4 options in a branch. The option_text is the line for the choice the player
    can make, and the events_text is everything that happens if the player chooses that option."""

    def __init__(self, option_text: str, option_number: int):
        self.text = option_text
        self.option_number = option_number


class Choice(Parseable):
    def __init__(self, option_1_text: str, option_2_text: str, option_3_text: str = None, option_4_text: str = None):
        self.option_1 = Option(option_1_text, 1)
        self.option_2 = Option(option_2_text, 2)
        self.option_3 = Option(option_3_text, 3)
        self.option_4 = Option(option_4_text, 4)

        self.active_options = [option for option in [self.option_1, self.option_2, self.option_3, self.option_4]
                               if option.text]

        self.number_of_options = len(self.active_options)
        if self.number_of_options == 4:
            self.space_between_lines = 40
        else:
            self.space_between_lines = 60

    def to_case_bodies(self) -> List[CaseBody]:
        """The main function, returning a list of cases for gamemaker code. All the other functions in this class
        are supporting this one."""
        return [self.setup_case(), self.display_options_case()] + self.instance_deactivate_cases()

    def setup_case(self) -> CaseBody:
        draw_texts = [self.draw_text_string(option) for option in self.active_options]
        remove_arrow = ["vicky_arrow_d.visible = false;"]
        instance_creates = [self.instance_create(option) for option in self.active_options]
        end = "step += 1;"

        return CaseBody("\n\t".join(draw_texts + remove_arrow + instance_creates + [end]))

    def draw_text_string(self, option: Option) -> str:
        """Used in multiple branch-related cases"""
        return 'draw_text(x, y + {space}, "Option {option_number}: {line}");'.format(
            space=str(self.space_between_lines * (option.option_number - 1)),
            option_number=option.option_number,
            line=option.text)

    def instance_create(self, option: Option) -> str:
        """Used in the initial, setup case"""
        space = self.space_between_lines * (option.option_number - 1)
        if option.option_number == 1:
            header = "option1 = instance_create(650, 620, obj_choice);"
        else:
            header = "option{num} = instance_create(option1.x, option1.y + {space}, obj_choice);".format(
                num=str(option.option_number), space=space)

        line = "option{num}.amount = {num};".format(num=str(option.option_number))
        return "\n\t".join([header, line])

    def display_options_case(self) -> CaseBody:
        draw_texts = [self.draw_text_string(option) for option in self.active_options]
        return CaseBody("\n\t".join(draw_texts))

    def instance_deactivate_cases(self) -> List[CaseBody]:
        def instance_deactivate_case(option) -> CaseBody:
            # header = 'draw_text(x, y, "{text}");'.format(text=option.events[0])
            body = """
        instance_deactivate_object(obj_choice);
        option = {option_number};
        vicky_arrow_d.visible = true;
        step += {remaining_steps};""".format(option_number=option.option_number,
                                             remaining_steps=self.number_of_options + 1 - option.option_number)
            return CaseBody(body)

        return [instance_deactivate_case(option) for option in self.active_options]


class Branch(Parseable):
    def __init__(self, option_1_parseables: List[Parseable], option_2_parseables: List[Parseable],
                 option_3_parseables: List[Parseable] = None, option_4_parseables: List[Parseable] = None):
        self.option_1_parseables = option_1_parseables
        self.option_2_parseables = option_2_parseables
        self.option_3_parseables = option_3_parseables
        self.option_4_parseables = option_4_parseables

        self.active_option_parseables = [opt for opt in [option_1_parseables, option_2_parseables, option_3_parseables,
                                                         option_4_parseables] if opt]
        self.num_options = len(self.active_option_parseables)
        # uprint("Branch active option parseables are {p}".format(p=self.active_option_parseables))

    def to_case_bodies(self) -> List[CaseBody]:
        uprint("Translating branch to case bodies")

        def parseable_to_flattened_cbs(pars: List[Parseable]) -> List[CaseBody]:
            return flatten([p.to_case_bodies() for p in pars])

        case_bodies = [parseable_to_flattened_cbs(par) for par in self.active_option_parseables]

        uprint("potato")
        uprint("case bodies are {case_bodies}".format(case_bodies=case_bodies))

        def header(pair: Tuple[List[Parseable], int]) -> str:
            return "if option = {num}".format(num=pair[1])

        def fill_empty_cases(bodies: List[CaseBody], num: int) -> List[CaseBody]:
            if len(bodies) <= num:
                extra_steps = [CaseBody("step += 1;")] * (num - len(bodies))
                return bodies + extra_steps
            else:
                raise ValueError

        max_option_length = max(len(cbs) for cbs in case_bodies)
        augmented_case_bodies = [fill_empty_cases(cb, max_option_length) for cb in case_bodies]
        numbered_option_pairs = zip(augmented_case_bodies, [1, 2, 3, 4])
        headers = [header(pair) for pair in numbered_option_pairs]

        def wrap_bodies(bodies: List[CaseBody], head: str) -> List[CaseBody]:
            return [CaseBody("\n".join([head, "{", body.text, "}"])) for body in bodies]

        debug_print_variable(augmented_case_bodies, "augmented_case_bodies")
        bodies_with_headers = zip(augmented_case_bodies, headers)
        wrapped_bodies = [wrap_bodies(b, h) for (b, h) in bodies_with_headers]
        uprint("Wrapped bodies are {wrapped_bodies}".format(wrapped_bodies=wrapped_bodies))

        # Need to transpose the list in order to put each line from each option into one case
        transposed = [list(i) for i in zip(*wrapped_bodies)]
        # print("\n Transposed is \n {transposed}".format(transposed=transposed))
        joined = [sum(row, CaseBody("")) for row in transposed]
        return joined


def case_body_to_single_string(cb: CaseBody) -> str:
    assert type(cb) == CaseBody, "Received a variable of type {t}".format(t=type(cb))
    return cb.text


def clean_raw_text(lines: List[str]) -> List[str]:
    stripped_lines = [l.strip() for l in lines]
    nonempty_lines = [l for l in stripped_lines if l != ""]
    replace_characters_unrecognized_by_gamemaker = [l.replace('“', "\"+\'\"").replace('”', '\"\'+\"').replace("’", "'")
                                                    for l in nonempty_lines]
    replace_ellipses = [l.replace("…", "...") for l in replace_characters_unrecognized_by_gamemaker]

    fix_capitalized_ifs = [l.replace("*If", "*if") for l in replace_ellipses]
    fix_capitalized_choices = [l.replace("*Choice", "*choice") for l in fix_capitalized_ifs]
    fix_capitalized_options = [l.replace("*Option", "*option") for l in fix_capitalized_choices]
    fix_capitalized_if_options = [l.replace("*if Option", "*if option") for l in fix_capitalized_options]
    def is_later_if_option(s: str) -> bool:
        return s.startswith("*if option") and (not s.startswith("*if option 1"))

    add_end_option_before_later_if_options = flatten(
        [l if not is_later_if_option(l) else ["*end if option*", l] for l in
         fix_capitalized_if_options])
    add_end_option_before_merge_option = flatten(
        [l if not l.startswith("*merge option*") else ["*end if option*", l] for l in
         add_end_option_before_later_if_options])
    return add_end_option_before_merge_option


def starts_with_normal_if(line: str) -> bool:
    return line.startswith("*if") and not line.startswith("*if option")


def find_first_unmatched(text: List[str], search_string: str, open_condition=starts_with_normal_if):
    if_counter = 0
    for index, line in enumerate(text):
        if open_condition(line):
            if_counter += 1
            print("Increasing if_counter to {if_counter} on line {line}".format(if_counter=if_counter, line=line))
        elif line.startswith("*{search}".format(search=search_string)):
            if_counter -= 1
            print("Decreasing if_counter to {if_counter} on line {line}".format(if_counter=if_counter, line=line))

        if if_counter < 0:
            return index

    if if_counter >= 0:
        raise ValueError(
            "{search_string} not found! Text was: \n {text}".format(search_string=search_string, text=text))


def starts_with_if_option_1(line: str) -> bool:
    return line.startswith("*if option 1")


def starts_with_any_if_option(line: str) -> bool:
    return line.startswith("*if option")


def parse_screen_line(line: str) -> Screen:
    # If the line contains a colon, find will return
    # the index. Otherwise it will return -1
    colon_index = line.find(":")
    line_contains_colon = True if colon_index > -1 else False
    if not line_contains_colon:
        return Screen(player, "Thinking",
                      Screen.split_text_into_multiple_lines(line))
    elif line_contains_colon:
        text_after_colon = line[colon_index + 1:].strip()
        return Screen(Character(line[:colon_index]), "Speaking",
                      Screen.split_text_into_multiple_lines(text_after_colon))


def clean_text_to_parseables(text: List[str]) -> List[Parseable]:
    if not text:
        return []
    for index, line in enumerate(text):
        uprint("text in current recursive iteration is {text}".format(text=text))
        remaining_text = text[1:]
        if remaining_text is None:
            remaining_text = []
        if line[0] == "(":
            return [Comment(line)] + clean_text_to_parseables(remaining_text)
        elif line[0] == "{":
            return [SpecificAction(line)] + clean_text_to_parseables(remaining_text)
        elif starts_with_normal_if(line):
            else_index = find_first_unmatched(text[index + 1:], search_string="else") + 1 + index
            merge_index = find_first_unmatched(text[index + 1:], search_string="merge if") + 1 + index
            condition_string = line.replace("*", "").strip()
            text_for_if_parseables = text[index + 1:else_index]
            text_for_else_parseables = text[else_index + 1:merge_index]
            if_parseables = clean_text_to_parseables(text_for_if_parseables)

            uprint("\n text for if parseables \n {t}".format(t=text_for_if_parseables))
            uprint("\n text for else parseables \n {t}".format(t=text_for_else_parseables))
            else_parseables = clean_text_to_parseables(text_for_else_parseables)
            return [IfElse(if_parseables, else_parseables, condition_string)] + clean_text_to_parseables(
                text[merge_index + 1:])
        elif line.startswith("*choice"):
            end_index = find_first_unmatched(text[index + 1:], search_string="end choice",
                                             open_condition=lambda line: line.startswith("*choice")) + index
            choice_raw_lines = remaining_text[:end_index]
            debug_print_variable(choice_raw_lines, "choice_raw_lines")
            choices = [choice[choice.rfind("*") + 1:] for choice in choice_raw_lines]
            uprint("\n choices going into Choice object \n {choices}".format(choices=choices))
            return [Choice(*choices)] + clean_text_to_parseables(text[end_index + 2:])

        elif line.startswith("*if option 1"):
            merge_index_in_remaining_text = find_first_unmatched(text[index + 1:], "merge option",
                                                                 open_condition=starts_with_if_option_1) + index + 1

            # merge_index_in_remaining_text = min(
            #     i for (i, l) in enumerate(remaining_text) if l.startswith("*merge option"))
            # Need to get up to 4 lists of parseables to feed into Branch

            def split_branch_text_into_option_sublists(lines: List[str]) -> List[List[str]]:
                if not lines:
                    return []
                else:
                    assert lines[0].startswith("*if option"), "Branch text must start with if option"
                    ind = find_first_unmatched(lines[1:], search_string="end if option",
                                               open_condition=starts_with_any_if_option)
                    option_text = lines[1:ind + 1]
                    return [option_text] + split_branch_text_into_option_sublists(lines[ind + 2:])

            # Split text into separate sublist for each if option

            uprint("\n Text going into splitter {t} \n".format(t=text[index:merge_index_in_remaining_text]))
            branch_texts = split_branch_text_into_option_sublists(text[index:merge_index_in_remaining_text])

            uprint("Branch texts are {branch_texts}".format(branch_texts=branch_texts))
            branch_parseables = [clean_text_to_parseables(t) for t in branch_texts]
            return [Branch(*branch_parseables)] + clean_text_to_parseables(
                remaining_text[merge_index_in_remaining_text + 1:])

        else:
            return [parse_screen_line(line)] + clean_text_to_parseables(remaining_text)


def debug_print_variable(var, name: str):
    uprint("\n {name} is \n {var}".format(name=name, var=var))


def case_bodies_to_output(case_bodies: List[CaseBody]) -> str:
    """Take all the case_bodies, which look like game_maker code, and make actual cases out of them!
    """

    # print("Case bodies are {case_bodies}".format(case_bodies=case_bodies))
    output_strings = []
    for (index, case) in enumerate(case_bodies):
        case_number = index + 1  # Offset python's 0-based indexing
        # print("Currently on case_number {case_number} \nBody is {case}".format(case_number=case_number, case=case))
        header = "\ncase {case_number}:".format(case_number=str(case_number))
        body = case.text
        end = "break;"
        output_strings += list_to_string([header, body, end])

    return "".join(output_strings)


if __name__ == "__main__":
    """This section sets up the command line arguments. """
    parser = argparse.ArgumentParser(description="Take the input and output filenames from the command line")
    parser.add_argument("-input")
    parser.add_argument("-output")
    args = parser.parse_args()

    """Opens the file and does the parsing."""
    with open(args.input, "r", encoding='utf8') as inFile:
        raw_text_from_file = inFile.readlines()
        uprint("File has {count} lines".format(count=len(raw_text_from_file)))
        cleaned_text = clean_raw_text(raw_text_from_file)
        uprint("File has {count} clean lines".format(count=len(cleaned_text)))
        parseables = clean_text_to_parseables(cleaned_text)
        for parseable in parseables:
            uprint("parseable is {p}".format(p=parseable.__dict__))

        case_bodies = flatten([parseable.to_case_bodies() for parseable in parseables])
        uprint("Starting to print case bodies \n\n")
        uprint(case_bodies)
        uprint("\n\n")
        output = case_bodies_to_output(case_bodies)
        pretty_output = jsbeautifier.beautify(output).replace("break;", "break;\n")
        with open(args.output, "w", encoding='utf8') as outFile:
            outFile.write(pretty_output)

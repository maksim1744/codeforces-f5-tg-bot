SHORT_SIZES = [3, 10, 4, 5]
LONG_SIZES = [9, 12, 11, 14]

SHORT_TITLES = ["№", "testset", "res", "tests"]
LONG_TITLES = ["problem", "testset", "verdict", "passed tests"]

SHORT_FMT = "|{{: ^{0}}}|{{: ^{1}}}|{{: ^{2}}}|{{: ^{3}}}|".format(*SHORT_SIZES)
LONG_FMT = "|{{: ^{0}}}|{{: ^{1}}}|{{: ^{2}}}|{{: ^{3}}}|".format(*LONG_SIZES)

def load_from_json(item):
    ID = item.get('id', 0)
    if item.get('author') is not None:
        if item['author'].get('members') is not None:
            if len(item['author']['members']) > 0:
                author = item['author']['members'][0]['handle']
    if item.get('problem') is not None:
        problem = item['problem'].get('index', '?')
    verdict = item.get('verdict', '?')
    testset = item.get('testset', '?')
    passed_test_count = item.get('passedTestCount', 0)

    if verdict.count('_') > 0:
        verdict = ''.join(verdict[i] for i in range(len(verdict)) if i == 0 or verdict[i - 1] == '_')
    if verdict == "TESTING":
        verdict = "..."

    return create_submission(ID, problem, author, verdict, testset, passed_test_count)

def create_submission(*args):
    res = '|'.join(str(arg) for arg in args)
    return res

def get_id(submission):
    return int(submission.split('|')[0])
def get_problem(submission):
    return submission.split('|')[1]
def get_author(submission):
    return submission.split('|')[2].lower()
def get_verdict(submission):
    return submission.split('|')[3]
def get_testset(submission):
    return submission.split('|')[4]
def get_passed_test_count(submission):
    return int(submission.split('|')[5])

def is_tested(submission):
    if get_verdict(submission) == "...":
        return False
    if get_verdict(submission) != "OK":
        return True
    if get_testset(submission) != "PRETESTS":
        return True
    return False

def get_titles(short=False):
    if short:
        return SHORT_FMT.format(*SHORT_TITLES) + "\n|" + "|".join("-" * s for s in SHORT_SIZES) + "|\n"
    else:
        return LONG_FMT.format(*LONG_TITLES) + "\n|" + "|".join("-" * s for s in LONG_SIZES) + "|\n"

def to_string(submission, short=False):
    if short:
        return SHORT_FMT.format(get_problem(submission), get_testset(submission), get_verdict(submission), get_passed_test_count(submission))
    else:
        return LONG_FMT.format(get_problem(submission), get_testset(submission), get_verdict(submission), get_passed_test_count(submission))

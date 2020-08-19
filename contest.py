import submission as sub

from time import sleep, clock
from threading import Thread

import requests
import json
import sys

class Contest(Thread):
    DOING_HARD_RESET = False

    MODE_INIT = 0
    MODE_GOING_BACK = 1

    PAGE_SIZE = 3000
    BLOCK_SIZE = 10000

    def reset(self):
        self.need_reset = True
        self.first_untested = 10**20
        self.from_ = 1

    def __init__(self, ID):
        Thread.__init__(self);
        self.sum_time = 0
        self.cnt_time = 0
        self.ID = ID
        self.running = True
        self.need_reset = False
        self.hard_refresher = ContestHardRefresher(self)
        self.hard_sum_time = 0
        self.hard_cnt_time = 0
        self.reset()
        self.start()

    def run(self):
        while self.running:
            if self.need_reset:
                self.data = dict()
                self.mode = Contest.MODE_INIT
                self.need_reset = False
            start_time = clock()
            self.update()
            delay = clock() - start_time
            if delay < 1:
                sleep(1 - delay)
            # print('from {}, first_untested {}'.format(self.from_, self.first_untested), flush=True)

    def stop(self):
        if self.hard_refresher.isAlive():
            self.hard_refresher.stop()
        self.running = False

    def hard_refresh(self):
        while Contest.DOING_HARD_RESET:
            sleep(5)
        t = clock()
        Contest.DOING_HARD_RESET = True
        # do something so no more that 1 contest is in MODE_INIT
        data = requests.get("https://codeforces.com/api/contest.status?contestId={}&from=1&count=1000000000".format(self.ID))
        # 2436 pages in status requires ~15Mb and ~11s (peak RAM ~300Mb)
        if not data.ok:
            Contest.DOING_HARD_RESET = False
            return False
        data = json.loads(data.text)
        if data["status"] != "OK":
            Contest.DOING_HARD_RESET = False
            return False

        for item in data["result"]:
            submission = sub.load_from_json(item)
            self.data.setdefault(sub.get_author(submission), dict())
            self.data[sub.get_author(submission)][sub.get_id(submission)] = submission
            if self.mode == Contest.MODE_INIT:
                self.first_untested = min(self.first_untested, sub.get_id(submission))

        if self.mode == Contest.MODE_INIT:
            self.mode = Contest.MODE_GOING_BACK
            self.from_ = max(1, len(data["result"]) - Contest.PAGE_SIZE // 2)
        # print('hard refresh done', flush=True)
        self.hard_sum_time += clock() - t
        self.hard_cnt_time += 1
        if self.hard_cnt_time % 10 == 0:
            print("average time on HARD REFRESH from {} queries: {}".format(self.hard_cnt_time, self.hard_sum_time / self.hard_cnt_time),
                flush=True)
            self.hard_cnt_time = 0
            self.hard_sum_time = 0
        Contest.DOING_HARD_RESET = False
        return True

    def update(self):
        if self.mode == Contest.MODE_INIT:
            if not self.hard_refresh():
                return
            if not self.hard_refresher.isAlive():
                self.hard_refresher.start()
        elif self.mode == Contest.MODE_GOING_BACK:
            t = clock()
            data = requests.get("https://codeforces.com/api/contest.status?contestId={}&from={}&count={}".format(
                                                                                        self.ID, self.from_, Contest.PAGE_SIZE))
            if not data.ok:
                return
            data = json.loads(data.text)
            if data["status"] != "OK":
                return

            if len(data["result"]) == 0:
                self.from_ = max(1, self.from_ - Contest.PAGE_SIZE // 2)
                return

            mn_id = 10**20
            mx_id = 0
            first_untested = 10**20
            first_untested_ind = 0

            for i, item in enumerate(data["result"]):
                submission = sub.load_from_json(item)
                self.data.setdefault(sub.get_author(submission), dict())
                self.data[sub.get_author(submission)][sub.get_id(submission)] = submission
                mn_id = min(mn_id, sub.get_id(submission))
                mx_id = max(mx_id, sub.get_id(submission))
                if not sub.is_tested(submission):
                    first_untested = min(first_untested, sub.get_id(submission))
                    first_untested_ind = len(data["result"]) - i
            if mn_id > self.first_untested:
                self.from_ += Contest.PAGE_SIZE // 2
            else:
                self.first_untested = first_untested
                if first_untested > mx_id:
                    self.from_ = max(1, self.from_ - Contest.PAGE_SIZE // 2)
                elif first_untested_ind > Contest.BLOCK_SIZE:
                    self.from_ = max(1, self.from_ - Contest.BLOCK_SIZE // 2)

            self.sum_time += clock() - t
            self.cnt_time += 1
            if self.cnt_time % 1000 == 0:
                print("average time on MODE_GOING_BACK from {} queries: {}".format(self.cnt_time, self.sum_time / self.cnt_time), flush=True)
                self.cnt_time = 0
                self.sum_time = 0


    def get_submissions(self, author):
        return sorted(self.data.get(author.lower(), dict()).values(), key=sub.get_id)



class ContestHardRefresher(Thread):
    def __init__(self, contest):
        Thread.__init__(self)
        self.contest = contest
        self.running = True

    def stop(self):
        self.running = False

    def run(self):
        while self.running:
            self.contest.hard_refresh()

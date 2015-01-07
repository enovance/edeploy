#
# Copyright (C) 2015 eNovance SAS <licensing@enovance.com>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import unittest

import verifyids


class TestVerifyids(unittest.TestCase):

    def test_uids_in_sync(self):
        etc_password = [{'gid': '1', 'user': 'foo', 'uid': '1'}, {'gid': '2', 'user': 'bar', 'uid': '2'}]
        root_ids_tables = [{'gid': '1', 'user': 'foo', 'uid': '1'}, {'gid': '2', 'user': 'bar', 'uid': '2'}]
        missing_uids = verifyids.find_missing_uids(etc_password, root_ids_tables)
        self.assertEquals(missing_uids, [])

    def test_uids_out_of_sync(self):
        etc_password = [{'gid': '1', 'user': 'foo', 'uid': '2'}]
        root_ids_tables = [{'gid': '2', 'user': 'foo', 'uid': '2'}]
        missing_uids = verifyids.find_missing_uids(etc_password, root_ids_tables)
        self.assertEquals(missing_uids, [{'gid': '1', 'user': 'foo', 'uid': '2'}])

if __name__ == "__main__":
    unittest.main()

# test_verifyids.py ends here

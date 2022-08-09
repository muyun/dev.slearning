import torch
import random
from tqdm import tqdm
import torch.utils.data as data
from transformers import GPT2Tokenizer, BertTokenizer
from collections import defaultdict


class WikihowDataset(data.Dataset):
    """WikiSection data"""


    def __init__(
            self,
            train,
            all_dataset,
            config,
            tokenizer_name="GPT2",
            seed=1,
    ):
        """
        """
        super().__init__()
        self.train = train
        self.all_dataset = all_dataset
        self.config=config

        if self.train:
            self.start_idx, self.end_idx = 0, 1000
        else:
            self.start_idx, self.end_idx = 40_000, 40_100
        self.seed = seed
        self.tokenizer_name = tokenizer_name
        self._set_tokenizer()
        print("Loading dataset...")
        self._process_data()
        print("Done loading dataset.")

    def _process_data(self):
        self.processed_data = []
        split_pattern = ".  "
        doc_counter = 0
        for doc_id in tqdm(range(self.start_idx, self.end_idx)):
            doc = self.all_dataset[doc_id]

            method2steps = defaultdict(list)
            # Wikihow has k different methods
            for _, v in doc['steps'].items():
                # section = one of the how-to methods
                method2steps[v['section']].append(v)

            for method_name, steps in method2steps.items():
                doc_info = []
                sentence_counter = 0
                # Put all the document sentences together.
                all_sentences = [self.section_ids[0] + " " + doc['title'] + " . "]
                all_sentences += [self.section_ids[1] + " " + method_name + " . "]
                for step_num, step in enumerate(steps):
                    directions = [ f"{self.section_ids[2]} {step_num} "
                        + step['summary'][:-1] + " . "]
                    sentences = [_ + " . " for _ in step['text'].split(split_pattern)]
                    if sentences[-1].endswith(". . "):
                        sentences[-1] = sentences[-1].replace('. . ', ' . ')
                    all_sentences += directions + sentences

                if not all([
                        len(self.tokenizer(s)['input_ids']) < 1024 for s in all_sentences]):
                    continue

                for sentence in all_sentences:
                    if not sentence:
                        continue
                    if sentence == ' . ':
                        continue
                    sentence_info = {
                        "sentence": sentence,
                        "sentence_id": sentence_counter,
                        "doc_id": doc_counter
                    }
                    doc_info.append(sentence_info)
                    sentence_counter += 1

                # Track total number of sentences in a document
                for info in doc_info:
                    info['total_doc_sentences'] = sentence_counter

                self.processed_data += doc_info
                doc_counter += 1

        print("Example: ", self.processed_data[0])
        print("Example: ", self.processed_data[10])

    def _set_tokenizer(self):
        if self.tokenizer_name == "GPT2":
            self.tokenizer = GPT2Tokenizer.from_pretrained('gpt2')
            self.tokenizer.pad_token = self.tokenizer.eos_token
            self.end_token = self.tokenizer.eos_token_id
            self.max_length = 1024
        elif self.tokenizer_name == "BERT":
            self.tokenizer = BertTokenizer.from_pretrained('bert-base-cased')
            self.max_length = 512
        else:
            raise ValueError("Dont recognize name {}".format(self.tokenizer_name))

        self.section_ids = [
            '[ TITLE ]',
            '[ METHOD ]',
            '[ STEP ]'
        ]
        self.section_names = self.section_ids
        self.cl_eos_str = " . "
        self.tokenizer.add_tokens(self.section_ids + [self.cl_eos_str])
        self.special_tokens = [_[0] for _ in self.tokenizer(self.section_ids)['input_ids']]
        self.cl_eos_id = self.tokenizer(self.cl_eos_str)['input_ids'][0]


    def tokenize_caption(self, caption, device):
        if self.tokenizer_name == "GPT2":
            output = self.tokenizer(
                caption,
                padding=True,
                return_tensors='pt',
            )
            input_ids = output['input_ids'].squeeze(0)
            attention_mask = output['attention_mask'].squeeze(0)
            eos_input_ids = torch.tensor([[self.end_token]*input_ids.shape[0]])
            eos_attention = torch.tensor([[0]*input_ids.shape[0]])
            input_ids = torch.cat((input_ids, eos_input_ids.T), dim=1)
            attention_mask = torch.cat((attention_mask, eos_attention.T), dim=1)
        elif self.tokenizer_name == "BERT":
            # Prepend [CLS] so I can use the first embedding
            output = self.tokenizer(
                caption,
                padding=True,
                return_tensors='pt',
            )
            input_ids = output['input_ids'].squeeze(0)
            attention_mask = output['attention_mask'].squeeze(0)
        return input_ids.to(device), attention_mask.to(device)

    def __len__(self):
        return len(self.processed_data) - 1

class WikihowDiscourse(WikihowDataset):
    def __init__(
            self,
            train,
            all_dataset,
            config,
            tokenizer_name="GPT2",
            seed=1,
    ):
        """
        """
        super(WikihowDiscourse, self).__init__(
            train=train,
            all_dataset=all_dataset,
            config=config,
            tokenizer_name=tokenizer_name,
            seed=seed,
        )

    def __getitem__(self, index):
        label = random.randint(0, 1) # either in- or out-of-order

        # SETUP 4: sample t+k utterance
        utterance = self.processed_data[index]
        tp1 = min(utterance['total_doc_sentences']-1, utterance['sentence_id']+self.config.data_params.k)
        t = max(0, tp1-self.config.data_params.k)

        y_t = self.processed_data[index + (t - utterance['sentence_id'])]
        y_tp1 = self.processed_data[index + (tp1 - utterance['sentence_id'])]

        assert y_t['doc_id'] == y_tp1['doc_id']

        y_t = y_t['sentence']
        y_tp1 = y_tp1['sentence']

        if label:
            pass # do nothing
        else:
            tmp = y_tp1
            y_tp1 = y_t
            y_t = tmp

        if self.one_hot_labels:
            labels = torch.zeros(2)
            labels[label] = 1.0
            label = labels

        result = {
            'y_t': y_t,
            'y_tp1': y_tp1,
            'label': label,
            'idx': index,
            't': index + (t - utterance['sentence_id']),
            'tp1': index + (tp1 - utterance['sentence_id']),
        }

        return result

class WikihowTriplet(WikihowDataset):

    def __init__(
            self,
            train,
            all_dataset,
            config,
            tokenizer_name="GPT2",
            seed=1,
    ):
        """
        """
        super(WikihowTriplet, self).__init__(
            train=train,
            all_dataset=all_dataset,
            config=config,
            tokenizer_name=tokenizer_name,
            seed=seed,
        )
        self.k = self.config.data_params.k

    def __getitem__(self, index):
        utterance = self.processed_data[index]
        sentence_num = utterance['sentence_id']

        # Check if index is start of a seq. If so -> +2
        if sentence_num == 0:
            index += 2
        if sentence_num == 1:
            index += 1

        # Update
        utterance = self.processed_data[index]
        sentence_num = utterance['sentence_id']

        # TRIAL 2: Sample all random points, t, t', t''
        T = sentence_num
        # t is a random point in between
        nums = list(range(T))
        t1 = random.choice(nums)
        nums.remove(t1)
        t2 = random.choice(nums)
        if t2 < t1:
            t = t2
            t2 = t1
            t1 = t

        assert t1 < t2 and t2 < T
        y_0 = self.processed_data[index - T + t1]['sentence']
        y_t = self.processed_data[index - T + t2]['sentence']
        y_T = self.processed_data[index]['sentence']

        t_ = t1
        t = t2

        total_doc = utterance['total_doc_sentences']
        result = {
            'y_0': y_0,
            'y_t': y_t,
            'y_T': y_T,
            't_': t_,
            't': t,
            'T': T,
            'total_t': total_doc,
        }
        return result



class WikihowTPK(WikihowDataset):

    def __init__(
            self,
            train,
            all_dataset,
            config,
            seed=1,
            tokenizer_name="GPT2",
    ):
        """
        """
        super(WikihowTPK, self).__init__(
            train=train,
            all_dataset=all_dataset,
            config=config,
            tokenizer_name=tokenizer_name,
            seed=seed,
        )

    def __getitem__(self, index):
        k = self.config.data_params.k
        if k == 1:
            if self.processed_data[index]['doc_id'] != self.processed_data[index+1]['doc_id']:
                index -= 1

            y_t = self.processed_data[index]['sentence']
            y_tp1 = self.processed_data[index+1]['sentence']
            t = self.processed_data[index]['sentence_id']/self.processed_data[index]['total_doc_sentences']
        else:
            # k sampling
            utterance = self.processed_data[index]
            tp1 = min(utterance['total_doc_sentences']-1,
                      utterance['sentence_id']+self.config.data_params.k)
            t = max(0, tp1-self.config.data_params.k)

            y_t = self.processed_data[index + (t - utterance['sentence_id'])]['sentence']
            y_tp1 = self.processed_data[index + (tp1 - utterance['sentence_id'])]['sentence']
            t = self.processed_data[index + (t - utterance['sentence_id'])]['sentence_id']/utterance['total_doc_sentences']

        y_tm1 = (self.processed_data[index] if (index - 1 < 0 or self.processed_data[index]['doc_id'] != self.processed_data[index-1]['doc_id']) else self.processed_data[index-1])
        y_tm1 = y_tm1['sentence']
        y_tm2 = (self.processed_data[index] if (index - 2 < 0 or self.processed_data[index]['doc_id'] != self.processed_data[index-2]['doc_id']) else self.processed_data[index-2])
        y_tm2 = y_tm2['sentence']
        y_tm3 = (self.processed_data[index] if (index - 3 < 0 or self.processed_data[index]['doc_id'] != self.processed_data[index-3]['doc_id']) else self.processed_data[index-3])
        y_tm3 = y_tm3['sentence']


        result = {
            'y_t': y_t,
            'y_tm1': y_tm1,
            'y_tm2': y_tm2,
            'y_tm3': y_tm3,
            'y_tpk': y_tp1,
        }
        return result

import os
from copy import copy
import argparse
import re
from utils import decimal_to_binary
import pickle
from regenerate import find_invalid_case
import torch

def parse_answer(dataset:str, content:str, task_info:tuple=None):
    def extract_math(string):
        results = []
        stack = []
        flag = r"\boxed{"
        string_copy = copy(string)
        idx = string_copy.find(flag)
        if idx == -1:
            print(f"math parse failed: \"{string}\"")
            return []
            # assert False, f"math parse failed: \"{string}\""
        output_flag = 0
        idx += len(flag)
        while idx < len(string):
            if string[idx] == '{':
                output_flag += 1
            elif string[idx] == '}' and output_flag == 0:
                results.append("".join(stack))
                stack.clear()
                idx = string_copy.find(flag, idx)
                if idx == -1:
                    break
                else:
                    idx += len(flag)
                    continue
            elif string[idx] == '}' and output_flag != 0:
                output_flag -= 1
            stack.append(string[idx])
            idx += 1
        return results

    if dataset == "mmlu":
        assert len(task_info) == 5
        if "Combined Answer".lower() in content.lower():
            return None
        pattern = r"\((\w+)\)|(\w+)\)"
        matches = re.findall(pattern, content)
        matches = [match[0] or match[1] for match in matches]
        solution_by_re = None
        # assert len(matches)<=1, str(len(matches))
        for match_str in matches[::-1]:
            solution_by_re = match_str.upper()
            if solution_by_re >= 'A' and solution_by_re <= 'D':
                break
            else:
                solution_by_re = None
        if len(matches) > 1:
            print("origin:",(content,),"parse:", solution_by_re)
        solution_by_item = [-1,-1,-1,-1]
        idx = 0
        for item in task_info[1:]:
            pos = content.lower().rfind(item.lower().strip())
            if pos >= 0:
                solution_by_item[idx] = pos
            idx += 1
        if max(solution_by_item) == -1:
            solution_by_item = None
        else:
            solution_by_item = ["A","B","C","D"][
                solution_by_item.index(max(solution_by_item))
            ]
        if solution_by_item is None and solution_by_re is not None:
            return solution_by_re
        elif solution_by_item is not None and solution_by_re is None:
            return solution_by_item
        elif solution_by_item is None and solution_by_re is None:
            return None
        elif solution_by_item is not None and solution_by_re is not None:
            if solution_by_item == solution_by_re:
                return solution_by_item
            else:
                return solution_by_item
    elif dataset == "math":
        # pattern = r"\\boxed{([^{}]+|(?R))*}"
        # matches = re.findall(pattern, content)
        matches = extract_math(string=content)
        if len(matches)==0:
            return None
        else:
            return matches[-1]
    elif dataset == "chess":
        none_responese = [
            "i am unable to provide a valid destination square based on the given chess game and moves",
            "none",
            "no valid",
            "no specific valid",
            "invalid",
            "n/a",
            "unable to provide",
            "game sequence contains errors",
            "i cannot provide"
        ]
        content = content.lower()
        pattern = r"[a-h][1-8]"
        pos = content.rfind("final answer")
        if pos != -1:
            item = content.split("final answer")[-1].strip()
            matches = re.findall(pattern, item)
            if len(matches) == 1:
                return matches[0].lower()
            elif len(matches) > 1:
                return matches[-1].lower()
            else:
                for valid_case in none_responese:
                    if valid_case in content:
                        return None
                return None
                assert False, f"chess parse failed 1: \"{content}\""
        else:
            matches = re.findall(pattern, content)
            if len(matches) == 0:
                for valid_case in none_responese:
                    if valid_case in content:
                        return None
                return None
                # assert False, f"chess parse failed 2: \"{content}\""
            else:
                return matches[-1]
    else:
        assert False

def parse_args():
    parser = argparse.ArgumentParser(description='agent')
    parser.add_argument('--dataset', type=str, default="mmlu") 
    parser.add_argument('--metric', type=str, default="acc")    
    # =========================================================================================
    parser.add_argument('--repeat', type=int, default=-1)     
    parser.add_argument('--experiment_type', type=str, default="main") 
    parser.add_argument('--turn', type=int, default=3)  
    parser.add_argument('--agent', type=int, default=3) 
    parser.add_argument('--role', type=str, default="[0,1,2,3]")  
    parser.add_argument('--n_case', type=int, default=50)
    parser.add_argument('--which_turn', type=int, default=-1)  
    return parser.parse_args()

def check_args(args):
    assert args.dataset.lower() in ["mmlu","chess","math"], \
        "invalid dataset"
    assert args.metric.lower() in ["dag", "acc", "token"], \
        "invalid metric"
    assert args.repeat == -1 or args.repeat >= 1, \
        "invalid repeat"
    assert isinstance(eval(args.role), list), \
        "invalid role"
    args.role = eval(args.role)
    return args

def load_dataset(args):
    # file_name = f"./results/{args.experiment_type}/{args.dataset}_data.pkl"
    file_name = f"./eval_data/{args.dataset}.pkl"
    database = pickle.load(open(file_name, "rb"))
    return database

def load_agent_file(args):
    def get_map_id(directory):
        files = os.listdir(directory)
        replace_mapping = {}
        for f in files:
            if "token" in f and "replace" in f:
                """3_harmony_3_agents_3_turns_111_strategy_case_56_replace_23_token.pkl"""
                items = f.split("_")
                print(items)
                if int(items[-2]) in replace_mapping:
                    assert replace_mapping[int(items[-2])] == int(items[-4])
                replace_mapping[int(items[-2])] = int(items[-4])
                assert int(items[-2])<args.n_case and int(items[-4]) >= args.n_case
        print(replace_mapping)
        return replace_mapping

    file_mapping = {}
    file_dir = f"./results/{args.experiment_type}/{args.dataset}"
    repeat_dir_name = os.listdir(file_dir)
    strategies = [decimal_to_binary(_, args.turn) for _ in range(2**args.turn)]
    if args.repeat != -1:
        assert str(args.repeat) in repeat_dir_name
        repeat_dir_name = [str(args.repeat)]
    invalid_case_id = []
    if args.repeat not in [4,5]:
        invalid_case_id = find_invalid_case(args)
    print(invalid_case_id)
    replace_mapping = get_map_id(f"{file_dir}/{repeat_dir_name[0]}")
    assert len(invalid_case_id) == len(replace_mapping)
    for repeat in repeat_dir_name:
        for role in args.role:
            for strategy in strategies:
                for case_id in range(args.n_case):
                    if case_id in invalid_case_id:
                        origin_file_name = f"{role}_harmony_{args.agent}_agents_{args.turn}_turns_{strategy}_strategy_case_{case_id}.pkl"
                        origin_full_path = f"{file_dir}/{repeat}/{origin_file_name}"
                        now_file_name = f"{role}_harmony_{args.agent}_agents_{args.turn}_turns_{strategy}_strategy_case_{replace_mapping[case_id]}_replace_{case_id}.pkl"
                        now_full_path = f"{file_dir}/{repeat}/{now_file_name}"
                        file_mapping[origin_full_path] = now_full_path
                    else:
                        file_name = f"{role}_harmony_{args.agent}_agents_{args.turn}_turns_{strategy}_strategy_case_{case_id}.pkl"
                        full_path = f"{file_dir}/{repeat}/{file_name}"
                        file_mapping[full_path] = full_path
    return file_mapping

def _most_frequence_answer(answers:list):
    # print(List)
    counter = 0
    if answers is None:
        return None
    num = [answers[0]]

    for i in answers:
        current_frequency = answers.count(i)
        if current_frequency > counter:
            counter = current_frequency
            num = [i]
        elif current_frequency == counter:
            num.append(i)

    num = list(set(num))
    if counter == 1:
        return None
    elif len(num) != 1:
        return None
    else:
        return num[0]

def judge_answer(agent_answer:list, gt_answer, args):
    math_pattern = [
        " \\text{ positive integers, } 12 \\text{ negative integers}", " \\, \\text{cm}", "\\, \\text{cm}",
        "^\\circ", "{\\text{Degree of }} g(x) = ", "°", " \\text{ cm}", "\\text{ cm}", "b = ", "r = ", "x = ", "m+n = ", "\\text{ degrees}", "x + y + z = "
    ]
    def check_math_answer(answer):
        if answer == '{2^3 \\times 3^2 \\times 5 \\times 7}':
            return '2520'
        for _ in math_pattern:
            answer = answer.replace(_, "")
        # answer = answer.replace("^\\circ", "").replace(" \\, \\text{cm}","").replace("{\\text{Degree of }} g(x) = ","")
        answer = answer.replace("{", "").replace("}", "")
        if answer in ["978,121", "99,940,009"]:
            return answer.replace(",", "")
        return answer

    def check_include(answers: list):
        """['{12}', '12', '24']"""
        for i in range(len(answers)):
            if answers[i] is not None:
                for _ in math_pattern:
                    answers[i] = answers[i].replace(_, "")
        for i in range(len(answers)):
            for j in range(len(answers)):
                if i != j and answers[i] is not None and answers[j] is not None and answers[i] in answers[j] and answers[i] != answers[j]:
                    if "{" + answers[i] + "}" == answers[j]:
                        answers[i] = answers[j]
        return answers

    # if args.dataset == "math":
    #     # _agent_answer = 
    #     agent_final_answer = _most_frequence_answer(answers=[check_math_answer(_) for _ in agent_answer])
    #     print(agent_final_answer)
    # else:
    if args.dataset == "math":
        agent_answer = check_include(agent_answer)
    agent_final_answer = _most_frequence_answer(answers=agent_answer)
    # print(agent_answer)
    # print(agent_final_answer, gt_answer)
    # assert False
    if agent_final_answer is None:
        return 0
    if args.dataset == "chess":
        assert isinstance(gt_answer, list)
        print("chess-check:", agent_final_answer)
        print("check-answer:", gt_answer)
        if agent_final_answer in gt_answer:
            return 1
        else:
            return 0
    elif args.dataset == "mmlu":
        if agent_final_answer.lower() == gt_answer.lower():
            return 1
        else:
            return 0
    elif args.dataset == "math":
        if isinstance(gt_answer, tuple):
            gt_answer = gt_answer[0]
        agent_final_answer = check_math_answer(agent_final_answer)
        if agent_final_answer.lower() == gt_answer.lower():
            print(agent_answer)
            print(agent_final_answer, gt_answer, "True")
            return 1
        else:
            print(agent_answer)
            print(agent_final_answer, gt_answer, "False")
            return 0
    else:
        assert False

def evaluate_in_acc(args):
    results_value = []
    results_name = []
    database = load_dataset(args)
    file_mapping = load_agent_file(args)
    file_dir = f"./results/{args.experiment_type}/{args.dataset}"
    repeat_dir_name = os.listdir(file_dir)
    strategies = [decimal_to_binary(_, args.turn) for _ in range(2 ** args.turn)]
    if args.repeat != -1:
        assert str(args.repeat) in repeat_dir_name
        repeat_dir_name = [str(args.repeat)]
    for repeat in repeat_dir_name:
        for role in args.role:
            for strategy in strategies:
                current_acc = 0
                for case_id in range(args.n_case):
                    origin_file_name = f"{role}_harmony_{args.agent}_agents_{args.turn}_turns_{strategy}_strategy_case_{case_id}.pkl"
                    origin_full_path = f"{file_dir}/{repeat}/{origin_file_name}"
                    now_full_path = file_mapping[origin_full_path]
                    try:
                        agent_center = pickle.load(open(now_full_path, "rb"))
                    except:
                        print("shutdown:",now_full_path)
                        current_acc += 0
                        continue
                    agent_answers = []
                    gt_answers = database["answer"][case_id]
                    for agent_id in range(args.agent):
                        context = agent_center[agent_id][args.which_turn]
                        assert context["role"] == "assistant"
                        agent_answers.append(
                            parse_answer(dataset=args.dataset, content=context["content"], task_info=database["task_info"][case_id])
                        )
                        # print(context, agent_answers[-1], gt_answers)
                    current_acc += judge_answer(agent_answer=agent_answers, gt_answer=gt_answers, args=args)
                results_name.append({'repeat': repeat, 'role': role, 'strategy': strategy})
                results_value.append(current_acc)
    for i in range(len(results_value)//(2**args.turn)):
        print(results_value[i*(2**args.turn):(i+1)*(2**args.turn)])
        # print(results_name)

def evaluate(args):
    func_mapping ={
        "acc": evaluate_in_acc,
    }
    func_mapping[args.metric](args=args)

def test():
    """mmlu"""
    # print(parse_answer(
    #     dataset="mmlu",
    #     task_info=("question", "8.05", "7.6", "3.95", "3.37"),
    #     content="After examining the solutions provided by other agents, I agree with their approach and reasoning. Here is an updated step-by-step analysis:\n\n1. We need to determine the highest amount of rainfall that would place the month among the 10% driest months.\n2. To do this, we calculate the z-score corresponding to the 10th percentile of the normal distribution.\n3. Using a standard normal distribution table or calculator, we find that the z-score for the 10th percentile is approximately -1.28.\n4. Next, we use the formula X = μ + (z * σ) to find the corresponding rainfall value.\n5. Plugging in the given values, we have X = 6 + (-1.28 * 1.6).\n6. Simplifying the equation, X ≈ 3.952 inches.\n7. Comparing the answer choices:\n   A) 8.05\n   B) 7.6\n   C) 3.95 (X)\n   D) 3.37\n8. Based on our calculations, the correct answer is C) 3.95 inches.\n\nSo, the final answer is C) 3.95 inches."))

    """chess"""
    # print(
    #     parse_answer(
    #         dataset="chess",
    #         content='After reviewing the valid move justifications provided by other agents and considering my previous answers, I acknowledge that my earlier suggestion of "d7" as the valid destination square was incorrect.\n\nConsidering the assessments from other agents, I agree that the valid destination square for the chess piece at is "d2". This move allows for capturing the opponent\'s piece on h6 (h6h5), which is a valid move according to the given chess game and position.\n\nAfter careful consideration, my final answer is "d2".'
    #     )
    # )

    print(
        parse_answer(
            dataset="math",
            content="After carefully considering the feedback and analysis provided by the other agents, I agree with the correction made by Agent 2 regarding the determinant of matrix $\\mathbf{M}$. The correct determinant is $\\boxed{-\\frac{25}{9}}$, as calculated by Agent 1 and Agent 2. I apologize for any confusion caused by my previous response."
        )
    )

    """majority vote"""
    for answers in [[None, None, 1], [1, 1, 2], [1, 2, 3], [1, 1, 2, 2], [None, None, 1, 1]]:
        print(_most_frequence_answer(answers))

if __name__ == '__main__':
    args = parse_args()
    args = check_args(args)
    evaluate(args)
    # test()
"""
python evaluate.py --dataset chess --metric acc --repeat 1
python evaluate.py --dataset math --metric acc --repeat 1
"""

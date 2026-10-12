import json
from openai import OpenAI
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

def analyze_email(content: str) -> dict:
    """分析邮件：分类、提取实体、总结"""
    if not content.strip():
        return {
            "intent": "other", "urgency": "low", 
            "entities": {}, "summary": "空邮件或无法解析"
        }

    system_prompt = """
    你是一个专业的外贸邮件分析助手。请阅读邮件内容，严格按 JSON 格式输出。
    
    必须分类为以下六类之一：inquiry, follow_up, complaint, sample_request, logistics, other。
    
    请提取以下实体信息（如果没有提取到，值填 null）：
    - customer_name: 客户名称或联系人
    - product_model: 产品编号或型号
    - quantity: 数量（包含单位）
    - delivery_date: 交期要求
    
    输出格式（不要输出任何多余文字，只返回纯 JSON）：
    {
      "intent": "分类英文名",
      "urgency": "high|medium|low",
      "summary": "一句话中文总结客户需求",
      "entities": {
        "customer_name": "...",
        "product_model": "...",
        "quantity": "...",
        "delivery_date": "..."
      }
    }
    """

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"邮件内容：\n{content}"}
        ],
        timeout=30,
        response_format={"type": "json_object"}
    )
    
    try:
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"intent": "other", "urgency": "low", "entities": {}, "summary": f"解析失败: {e}"}

def generate_reply_draft(content: str, analysis: dict) -> str:
    """根据分析结果生成回复草稿"""
    intent = analysis.get("intent", "other")
    entities = analysis.get("entities", {})
    
    system_prompt = f"""
    你是一个资深的外贸业务员。请根据客户来信和已提取的信息，撰写一封回复草稿。
    
    已知信息：
    - 客户意图：{intent}
    - 产品型号：{entities.get('product_model', '未提供')}
    - 数量：{entities.get('quantity', '未提供')}
    - 交期：{entities.get('delivery_date', '未提供')}
    
    要求：
    1. 语气专业热情，使用与来信相同的语言。
    2. 如果是询盘，感谢客户对相关产品的询价，告知会尽快核算报价。
    3. 如果是投诉，表达歉意并承诺立即调查。
    4. 绝对不要编造价格和具体交期，用 [请在此填写真实报价] 占位。
    5. 包含主题建议、称呼、正文、结尾。
    """
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"客户来信内容：\n{content}"}
        ],
        timeout=45
    )
    return response.choices[0].message.content
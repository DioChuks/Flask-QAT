import os
import re

def read_feedback_file():
  """
  Reads the feedback text file, removes code blocks and excessive newlines, and prints the cleaned text.
  """
  try:
    with open(os.path.join('research/', 'feedback.txt'), 'r') as f:
      # Read the entire file content as a string
      text = f.read()

      # Try different regular expressions (comment out unnecessary lines)
      text = re.sub(r"(?m)^`.*?`\n", "", text)  # With newline at the end
      text = re.sub(r"^`.*?`$", "", text)  # Without newline (if applicable)

      # Remove excessive newlines
      text = re.sub(r"\n\n+", "\n", text)

    print(text)
    print("cleaned text above")
  except FileNotFoundError:
    print("Error: File 'research/feedback.txt' not found")

read_feedback_file()

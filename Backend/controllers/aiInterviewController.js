import axios from "axios";

const AI_BACKEND_URL = "http://localhost:8000";

export const scheduleInterview = async (req, res) => {
  try {

    const { candidateEmail, jobId } = req.body;

    const response = await axios.post(
      `${AI_BACKEND_URL}/api/interviews/schedule`,
      {
        candidate_email: candidateEmail,
        job_id: jobId
      }
    );

    res.json(response.data);

  } catch (error) {

    console.error("AI Interview Scheduling Error:", error);

    res.status(500).json({
      message: "Failed to schedule interview"
    });

  }
};
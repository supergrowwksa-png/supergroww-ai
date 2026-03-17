const axios = require("axios");
const Job = require("../models/Job");
const User = require("../models/User");

exports.startInterview = async (req, res) => {
  try {
    const { jobId } = req.params;

    // Candidate info
    const candidate = await User.findById(req.user.id);

    if (!candidate) {
      return res.status(404).json({ message: "Candidate not found" });
    }

    // Job info
    const job = await Job.findById(jobId);

    if (!job) {
      return res.status(404).json({ message: "Job not found" });
    }

    // Prepare payload for AI service
    const payload = {
      candidate_name: candidate.name,
      candidate_email: candidate.email,
      resume_url: candidate.resume || "",
      job_title: job.title,
      job_description: job.description,
      skills: job.skills || []
    };

    // Call AI Interview Backend
    const response = await axios.post(
      "http://localhost:8000/start-interview",
      payload
    );

    return res.json({
      success: true,
      roomName: response.data.room_name,
      token: response.data.token,
      ws_url: response.data.ws_url
    });

  } catch (error) {
    console.error("Start Interview Error:", error.message);
    res.status(500).json({ message: "Failed to start interview" });
  }
};